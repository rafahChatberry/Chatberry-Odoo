import json
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ChatberryWhatsappMessageLog(models.Model):
    _name = "chatberry.whatsapp.message.log"
    _description = "Chatberry WhatsApp Message Log"
    _order = "create_date desc, id desc"
    _rec_name = "display_name"

    display_name = fields.Char(compute="_compute_display_name")
    status = fields.Selection([
        ("queued", "Queued"),
        ("sending", "Sending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
        ("cancelled", "Cancelled"),
    ], default="queued", required=True, index=True)
    reason_code = fields.Selection([
        ("automation_disabled", "Automation Disabled"),
        ("no_automation", "No Automation"),
        ("inactive_automation", "Inactive Automation"),
        ("inactive_template", "Inactive Template"),
        ("company_mismatch", "Company Mismatch"),
        ("team_mismatch", "Team Mismatch"),
        ("stage_from_mismatch", "Stage From Mismatch"),
        ("creation_disabled", "Creation Disabled"),
        ("duplicate", "Duplicate Prevented"),
        ("no_phone", "No Phone"),
        ("mapping_error", "Variable Mapping Error"),
        ("media_error", "Header Media Error"),
        ("api_config_error", "API Configuration Error"),
        ("api_request_error", "API Request Error"),
        ("missing_reference", "Missing Reference"),
        ("max_retries", "Max Retries Reached"),
        ("unknown", "Unknown"),
    ], string="Reason", index=True, readonly=True)
    lead_id = fields.Many2one("crm.lead", ondelete="cascade", index=True)
    automation_id = fields.Many2one("chatberry.crm.stage.automation", ondelete="set null", index=True)
    template_id = fields.Many2one("chatberry.whatsapp.template", ondelete="set null", index=True)
    from_stage_id = fields.Many2one("crm.stage", string="From Stage", ondelete="set null")
    to_stage_id = fields.Many2one("crm.stage", string="To Stage", ondelete="set null", index=True)
    phone = fields.Char(index=True)
    payload_json = fields.Text(readonly=True)
    response_text = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)
    attempts = fields.Integer(default=0, readonly=True)
    max_attempts = fields.Integer(default=3)
    next_retry_date = fields.Datetime(index=True)
    sent_date = fields.Datetime(readonly=True)
    dedupe_key = fields.Char(index=True, copy=False)

    _sql_constraints = [
        ("dedupe_key_unique", "unique(dedupe_key)", "This CRM WhatsApp automation was already queued."),
    ]

    @api.depends("lead_id", "template_id", "status")
    def _compute_display_name(self):
        for log in self:
            log.display_name = "%s - %s - %s" % (
                log.lead_id.display_name or "CRM Lead",
                log.template_id.display_name or "WhatsApp",
                log.status,
            )

    def action_retry(self):
        for log in self.filtered(lambda item: item.status in ("failed", "cancelled")):
            log.write({
                "status": "queued",
                "next_retry_date": False,
                "error_message": False,
            })

    def action_cancel(self):
        self.filtered(lambda item: item.status in ("queued", "failed")).write({"status": "cancelled"})

    def action_force_resend(self):
        for log in self:
            log.copy({
                "status": "queued",
                "reason_code": False,
                "attempts": 0,
                "next_retry_date": False,
                "sent_date": False,
                "payload_json": False,
                "response_text": False,
                "error_message": False,
                "dedupe_key": False,
            })

    @api.model
    def _cron_process_queue(self):
        Param = self.env["ir.config_parameter"].sudo()
        if Param.get_param("pos_webhook_notify.enable_crm", "True") != "True":
            _logger.info("[CHATBERRY:CRM:QUEUE] CRM WhatsApp Automation is disabled; queue processing skipped.")
            return

        batch_size = self._safe_int(Param.get_param("pos_webhook_notify.crm_queue_batch_size", "20"), 20)
        now = fields.Datetime.now()
        logs = self.search([
            ("status", "in", ("queued", "failed")),
            "|",
            ("next_retry_date", "=", False),
            ("next_retry_date", "<=", now),
        ], order="create_date asc, id asc", limit=batch_size)

        for log in logs:
            if log.attempts >= log.max_attempts:
                if not log.reason_code:
                    try:
                        with self.env.cr.savepoint():
                            log.write({
                                "reason_code": "max_retries",
                                "error_message": "Max retry attempts reached.",
                            })
                    except Exception:
                        _logger.exception(
                            "[CHATBERRY:CRM:QUEUE] Failed to mark max retries. "
                            "This can indicate database/schema/access issues. log_id=%s",
                            log.id,
                        )
                continue
            try:
                with self.env.cr.savepoint():
                    log._process_one()
            except Exception:
                _logger.exception(
                    "[CHATBERRY:CRM:QUEUE] Queue processing crashed before the log could be updated. "
                    "This can indicate database/schema/access issues. log_id=%s",
                    log.id,
                )

    def _process_one(self):
        self.ensure_one()
        if not self.lead_id or not self.automation_id or not self.template_id:
            _logger.warning(
                "[CHATBERRY:CRM:QUEUE] Missing required reference lead_id=%s automation_id=%s template_id=%s log_id=%s",
                self.lead_id.id if self.lead_id else False,
                self.automation_id.id if self.automation_id else False,
                self.template_id.id if self.template_id else False,
                self.id,
            )
            self.write({"attempts": self.attempts + 1})
            self._mark_failed("Missing lead, automation, or template.", "missing_reference")
            return
        if not self.phone:
            phone = self.automation_id._resolve_recipient_phone(self.lead_id)
            if phone:
                self.write({"phone": phone})
        if not self.phone:
            _logger.warning(
                "[CHATBERRY:CRM:QUEUE] No phone number found lead_id=%s automation_id=%s log_id=%s strategy=%s",
                self.lead_id.id,
                self.automation_id.id,
                self.id,
                self.automation_id.recipient_strategy,
            )
            self.write({"attempts": self.attempts + 1})
            self._mark_failed("No phone number found for selected recipient strategy.", "no_phone")
            return

        try:
            self.write({
                "status": "sending",
                "reason_code": False,
                "attempts": self.attempts + 1,
                "error_message": False,
            })
            payload = self.env["chatberry.whatsapp.payload.builder"].build_payload(
                self.template_id,
                self.lead_id,
                self.phone,
            )
            response = self.env["chatberry.whatsapp.sender"].send_payload(payload)
            self.write({
                "status": "sent",
                "payload_json": json.dumps(payload, indent=2),
                "response_text": response.get("body"),
                "sent_date": fields.Datetime.now(),
                "next_retry_date": False,
            })
        except Exception as error:
            _logger.exception("[CHATBERRY:CRM:QUEUE] Failed to send log %s", self.id)
            self._mark_failed(str(error), self._guess_failure_reason(error))

    def _mark_failed(self, message, reason_code=False):
        retry_delay = self._safe_int(
            self.env["ir.config_parameter"].sudo().get_param("pos_webhook_notify.crm_retry_delay_minutes", "15"),
            15,
        )
        values = {
            "status": "failed",
            "reason_code": reason_code or "unknown",
            "error_message": message[:2000] if message else "Unknown error",
        }
        if self.attempts < self.max_attempts:
            values["next_retry_date"] = fields.Datetime.now() + timedelta(minutes=retry_delay)
        else:
            values["next_retry_date"] = False
        self.write(values)

    def _guess_failure_reason(self, error):
        message = str(error or "")
        lowered = message.lower()
        if "whatsapp api url is not configured" in lowered or "authorization" in lowered or "token" in lowered:
            return "api_config_error"
        if "cloudinary" in lowered or "header attachment" in lowered or "header media" in lowered:
            return "media_error"
        if "field path" in lowered or "does not exist on model" in lowered or "required variable" in lowered:
            return "mapping_error"
        if "http" in lowered or "connection" in lowered or "timeout" in lowered or "request" in lowered:
            return "api_request_error"
        return "unknown"

    @api.model
    def _safe_int(self, value, default):
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return default
