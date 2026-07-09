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
                continue
            log._process_one()

    def _process_one(self):
        self.ensure_one()
        if not self.lead_id or not self.automation_id or not self.template_id:
            self.write({"attempts": self.attempts + 1})
            self._mark_failed("Missing lead, automation, or template.")
            return
        if not self.phone:
            self.write({"attempts": self.attempts + 1})
            self._mark_failed("No phone number found for selected recipient strategy.")
            return

        try:
            self.write({"status": "sending", "attempts": self.attempts + 1, "error_message": False})
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
            self._mark_failed(str(error))

    def _mark_failed(self, message):
        retry_delay = self._safe_int(
            self.env["ir.config_parameter"].sudo().get_param("pos_webhook_notify.crm_retry_delay_minutes", "15"),
            15,
        )
        values = {
            "status": "failed",
            "error_message": message[:2000] if message else "Unknown error",
        }
        if self.attempts < self.max_attempts:
            values["next_retry_date"] = fields.Datetime.now() + timedelta(minutes=retry_delay)
        else:
            values["next_retry_date"] = False
        self.write(values)

    @api.model
    def _safe_int(self, value, default):
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return default
