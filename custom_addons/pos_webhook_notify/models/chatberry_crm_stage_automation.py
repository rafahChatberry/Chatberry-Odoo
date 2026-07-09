from odoo import api, fields, models


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
        default=True,
        help="Send when a new CRM lead/opportunity is created directly in Stage To.",
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
        if not leads or not self._get_enabled():
            return

        Log = self.env["chatberry.whatsapp.message.log"].sudo()
        max_attempts = self._get_default_max_attempts()
        for lead in leads:
            old_stage = old_stage_by_id.get(lead.id)
            new_stage = lead.stage_id
            if not new_stage or old_stage == new_stage:
                continue

            for automation in self._matching_automations(lead, old_stage, new_stage):
                phone = automation._resolve_recipient_phone(lead)
                dedupe_key = automation._make_dedupe_key(lead, new_stage)
                if automation.duplicate_policy == "once_per_stage" and Log.search_count([("dedupe_key", "=", dedupe_key)]):
                    Log.create({
                        "status": "skipped",
                        "lead_id": lead.id,
                        "automation_id": automation.id,
                        "template_id": automation.template_id.id,
                        "from_stage_id": old_stage.id if old_stage else False,
                        "to_stage_id": new_stage.id,
                        "phone": phone,
                        "error_message": "Duplicate prevented for this lead, automation, and target stage.",
                    })
                    continue

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
                log._process_one()

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
