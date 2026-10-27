import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ChatberryCrmStageAutomation(models.Model):
    _name = "chatberry.crm.stage.automation"
    _description = "Chatberry CRM Stage Automation"
    _order = "sequence, name, id"

    name = fields.Char(compute="_compute_name", store=True, readonly=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    team_id = fields.Many2one("crm.team", string="Sales Team")
    to_stage_id = fields.Many2one("crm.stage", string="Stage To", required=True, ondelete="cascade")
    from_stage_ids = fields.Many2many(
        "crm.stage",
        "chatberry_crm_automation_from_stage_rel",
        "automation_id",
        "stage_id",
        string="Stage From",
        help="Leave empty to match any previous stage. Creation events only match when this is empty.",
    )
    trigger_on_create = fields.Boolean(
        string="Send On Creation",
        default=False,
        help="Legacy option. CRM messages are not sent on record creation; use Send On Lead Conversion instead.",
    )
    trigger_on_conversion = fields.Boolean(
        string="Send On Lead Conversion",
        default=False,
        help="Send when a lead is converted into an opportunity in Stage To. Stage From must be empty.",
    )
    template_id = fields.Many2one("chatberry.whatsapp.template", required=True, ondelete="restrict")
    recipient_strategy = fields.Selection([
        ("first_available", "First Available"),
        ("lead_mobile", "Lead Mobile"),
        ("lead_phone", "Lead Phone"),
        ("partner_mobile", "Partner Mobile"),
        ("partner_phone", "Partner Phone"),
    ], default="first_available", required=True)
    duplicate_policy = fields.Selection([
        ("once_per_stage", "Once Per Lead and Stage"),
        ("every_transition", "Every Transition"),
    ], default="once_per_stage", required=True)
    log_ids = fields.One2many("chatberry.whatsapp.message.log", "automation_id")
    log_count = fields.Integer(compute="_compute_log_count")

    @api.depends("to_stage_id", "template_id", "team_id")
    def _compute_name(self):
        for automation in self:
            parts = [automation.to_stage_id.display_name or "CRM Stage"]
            if automation.team_id:
                parts.append(automation.team_id.display_name)
            if automation.template_id:
                parts.append(automation.template_id.display_name)
            automation.name = " / ".join(parts)

    def _compute_log_count(self):
        grouped = self.env["chatberry.whatsapp.message.log"].read_group(
            [("automation_id", "in", self.ids)],
            ["automation_id"],
            ["automation_id"],
        )
        counts = {row["automation_id"][0]: row["automation_id_count"] for row in grouped}
        for automation in self:
            automation.log_count = counts.get(automation.id, 0)

    def action_open_logs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "WhatsApp Logs",
            "res_model": "chatberry.whatsapp.message.log",
            "view_mode": "list,form",
            "domain": [("automation_id", "=", self.id)],
            "context": {"default_automation_id": self.id},
        }

    def action_open_template_mapping(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "WhatsApp Template Mapping",
            "res_model": "chatberry.whatsapp.template",
            "view_mode": "form",
            "res_id": self.template_id.id,
            "target": "current",
        }

    @api.model
    def _get_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "pos_webhook_notify.enable_crm", "True"
        ) == "True"

    @api.model
    def _get_default_max_attempts(self):
        value = self.env["ir.config_parameter"].sudo().get_param(
            "pos_webhook_notify.crm_max_retries", "3"
        )
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return 3

    @api.model
    def _queue_for_stage_changes(self, leads, old_stage_by_id):
        if not leads:
            return

        Log = self.env["chatberry.whatsapp.message.log"].sudo()
        max_attempts = self._get_default_max_attempts()
        for lead in leads:
            old_stage = old_stage_by_id.get(lead.id)
            new_stage = lead.stage_id
            if not new_stage or old_stage == new_stage:
                continue

            _logger.info(
                "[CHATBERRY:CRM:STAGE] Processing stage change lead_id=%s old_stage_id=%s new_stage_id=%s",
                lead.id,
                old_stage.id if old_stage else False,
                new_stage.id,
            )
            try:
                self._queue_for_single_stage_change(
                    lead, old_stage, new_stage, Log, max_attempts, event_type="stage_change"
                )
            except Exception:
                _logger.exception(
                    "[CHATBERRY:CRM:STAGE] Stage automation failed before a WhatsApp log could be completed. "
                    "This can indicate database/schema/access/constraint issues. lead_id=%s old_stage_id=%s new_stage_id=%s",
                    lead.id,
                    old_stage.id if old_stage else False,
                    new_stage.id,
                )

    @api.model
    def _queue_for_conversions(self, leads):
        if not leads:
            return

        Log = self.env["chatberry.whatsapp.message.log"].sudo()
        max_attempts = self._get_default_max_attempts()
        for lead in leads:
            if not lead.stage_id:
                continue
            _logger.info(
                "[CHATBERRY:CRM:CONVERSION] Processing lead conversion lead_id=%s stage_id=%s",
                lead.id,
                lead.stage_id.id,
            )
            try:
                self._queue_for_single_stage_change(
                    lead, False, lead.stage_id, Log, max_attempts, event_type="conversion"
                )
            except Exception:
                _logger.exception(
                    "[CHATBERRY:CRM:CONVERSION] Conversion automation failed. lead_id=%s stage_id=%s",
                    lead.id,
                    lead.stage_id.id,
                )

    @api.model
    def _queue_for_single_stage_change(
        self, lead, old_stage, new_stage, Log, max_attempts, event_type="stage_change"
    ):
        if not self._get_enabled():
            self._create_diagnostic_log(
                lead,
                old_stage,
                new_stage,
                "automation_disabled",
                "CRM WhatsApp Automation is disabled in Chatberry settings.",
            )
            return

        matching_automations = self.env["chatberry.crm.stage.automation"]
        candidate_automations = self.sudo().with_context(active_test=False).search([("to_stage_id", "=", new_stage.id)])
        if not candidate_automations:
            self._create_diagnostic_log(
                lead,
                old_stage,
                new_stage,
                "no_automation",
                "No CRM WhatsApp automation is configured for target stage '%s'." % new_stage.display_name,
            )
            return

        for automation in candidate_automations:
            reason_code, message = automation._get_skip_reason(lead, old_stage, event_type)
            if reason_code:
                automation._create_diagnostic_log(lead, old_stage, new_stage, reason_code, message)
            else:
                matching_automations |= automation

        for automation in matching_automations:
            phone = automation._resolve_recipient_phone(lead)
            dedupe_key = automation._make_dedupe_key(lead, new_stage)
            if automation.duplicate_policy == "once_per_stage" and Log.search_count([("dedupe_key", "=", dedupe_key)]):
                automation._create_diagnostic_log(
                    lead,
                    old_stage,
                    new_stage,
                    "duplicate",
                    "Duplicate prevented for this lead, automation, and target stage.",
                    phone=phone,
                )
                continue

            try:
                with self.env.cr.savepoint():
                    log = Log.create({
                        "status": "queued",
                        "lead_id": lead.id,
                        "automation_id": automation.id,
                        "template_id": automation.template_id.id,
                        "from_stage_id": old_stage.id if old_stage else False,
                        "to_stage_id": new_stage.id,
                        "phone": phone,
                        "dedupe_key": dedupe_key,
                        "max_attempts": max_attempts,
                    })
            except Exception:
                _logger.exception(
                    "[CHATBERRY:CRM:STAGE] Failed to create WhatsApp queue log. "
                    "This can indicate database/schema/access/constraint issues. lead_id=%s automation_id=%s "
                    "template_id=%s from_stage_id=%s to_stage_id=%s",
                    lead.id,
                    automation.id,
                    automation.template_id.id,
                    old_stage.id if old_stage else False,
                    new_stage.id,
                )
                continue

            try:
                with self.env.cr.savepoint():
                    log._process_one()
            except Exception:
                _logger.exception(
                    "[CHATBERRY:CRM:STAGE] Failed while processing WhatsApp log. "
                    "log_id=%s lead_id=%s automation_id=%s",
                    log.id,
                    lead.id,
                    automation.id,
                )

    def _get_skip_reason(self, lead, old_stage, event_type="stage_change"):
        self.ensure_one()
        if not self.active:
            return "inactive_automation", "Automation rule '%s' is inactive." % (self.display_name or self.id)
        if not self.template_id:
            return "missing_reference", "Automation has no WhatsApp template configured."
        if not self.template_id.active:
            return "inactive_template", "WhatsApp template '%s' is inactive." % self.template_id.display_name
        if lead.company_id and self.company_id and self.company_id != lead.company_id:
            return (
                "company_mismatch",
                "Automation company '%s' does not match lead company '%s'."
                % (self.company_id.display_name, lead.company_id.display_name),
            )
        if lead.team_id and self.team_id and self.team_id != lead.team_id:
            return (
                "team_mismatch",
                "Automation team '%s' does not match lead team '%s'."
                % (self.team_id.display_name, lead.team_id.display_name),
            )
        if not old_stage:
            if self.from_stage_ids:
                return "stage_from_mismatch", "Creation/conversion events only match automations with empty Stage From."
            if event_type == "conversion" and not self.trigger_on_conversion:
                return "conversion_disabled", "Lead was converted in this stage, but Send On Lead Conversion is disabled."
            if event_type != "conversion" and not self.trigger_on_create:
                return "creation_disabled", "Creation-triggered CRM sends are disabled."
            return False, False
        if self.from_stage_ids and old_stage not in self.from_stage_ids:
            return (
                "stage_from_mismatch",
                "Lead moved from '%s', but this automation only allows Stage From: %s."
                % (old_stage.display_name, ", ".join(self.from_stage_ids.mapped("display_name"))),
            )
        return False, False

    def _create_diagnostic_log(self, lead, old_stage, new_stage, reason_code, message, phone=False):
        self.ensure_one() if self else None
        automation_id = self.id if self else False
        _logger.info(
            "[CHATBERRY:CRM:DIAGNOSTIC] Skipping WhatsApp send lead_id=%s automation_id=%s "
            "from_stage_id=%s to_stage_id=%s reason=%s message=%s",
            lead.id if lead else False,
            automation_id,
            old_stage.id if old_stage else False,
            new_stage.id if new_stage else False,
            reason_code or "unknown",
            message,
        )
        try:
            with self.env.cr.savepoint():
                self.env["chatberry.whatsapp.message.log"].sudo().create({
                    "status": "skipped",
                    "reason_code": reason_code or "unknown",
                    "lead_id": lead.id if lead else False,
                    "automation_id": automation_id,
                    "template_id": self.template_id.id if self and self.template_id else False,
                    "from_stage_id": old_stage.id if old_stage else False,
                    "to_stage_id": new_stage.id if new_stage else False,
                    "phone": phone or False,
                    "error_message": message[:2000] if message else "Skipped before sending.",
                })
        except Exception:
            _logger.exception(
                "[CHATBERRY:CRM:DIAGNOSTIC] Failed to create skipped WhatsApp log. "
                "This can indicate database/schema/access/constraint issues. lead_id=%s automation_id=%s "
                "from_stage_id=%s to_stage_id=%s reason=%s",
                lead.id if lead else False,
                automation_id,
                old_stage.id if old_stage else False,
                new_stage.id if new_stage else False,
                reason_code or "unknown",
            )

    @api.model
    def _matching_automations(self, lead, old_stage, new_stage):
        domain = [
            ("active", "=", True),
            ("to_stage_id", "=", new_stage.id),
            ("template_id.active", "=", True),
        ]
        if lead.company_id:
            domain += ["|", ("company_id", "=", False), ("company_id", "=", lead.company_id.id)]
        if lead.team_id:
            domain += ["|", ("team_id", "=", False), ("team_id", "=", lead.team_id.id)]

        automations = self.search(domain)
        if not old_stage:
            return automations.filtered(
                lambda automation: automation.trigger_on_create and not automation.from_stage_ids
            )
        return automations.filtered(
            lambda automation: not automation.from_stage_ids or old_stage in automation.from_stage_ids
        )

    def _make_dedupe_key(self, lead, stage):
        self.ensure_one()
        if self.duplicate_policy == "once_per_stage":
            return "crm:%s:%s:%s" % (lead.id, self.id, stage.id)
        return "crm:%s:%s:%s:%s" % (lead.id, self.id, stage.id, fields.Datetime.now())

    def _resolve_recipient_phone(self, lead):
        self.ensure_one()
        values = {
            "lead_mobile": lead.mobile,
            "lead_phone": lead.phone,
            "partner_mobile": lead.partner_id.mobile,
            "partner_phone": lead.partner_id.phone,
        }
        if self.recipient_strategy == "first_available":
            for key in ("lead_mobile", "lead_phone", "partner_mobile", "partner_phone"):
                if values.get(key):
                    return values[key]
            return False
        return values.get(self.recipient_strategy)
