from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    chatberry_whatsapp_log_ids = fields.One2many(
        "chatberry.whatsapp.message.log",
        "lead_id",
        string="Chatberry WhatsApp Logs",
    )
    chatberry_whatsapp_log_count = fields.Integer(compute="_compute_chatberry_whatsapp_log_count")
    chatberry_last_whatsapp_status = fields.Selection(
        [
            ("queued", "Queued"),
            ("sending", "Sending"),
            ("sent", "Sent"),
            ("failed", "Failed"),
            ("skipped", "Skipped"),
            ("cancelled", "Cancelled"),
        ],
        compute="_compute_chatberry_last_whatsapp_log",
        string="Last WhatsApp Status",
        readonly=True,
    )
    chatberry_last_whatsapp_log_id = fields.Many2one(
        "chatberry.whatsapp.message.log",
        compute="_compute_chatberry_last_whatsapp_log",
    )

    def _compute_chatberry_whatsapp_log_count(self):
        grouped = self.env["chatberry.whatsapp.message.log"].read_group(
            [("lead_id", "in", self.ids)],
            ["lead_id"],
            ["lead_id"],
        )
        counts = {row["lead_id"][0]: row["lead_id_count"] for row in grouped}
        for lead in self:
            lead.chatberry_whatsapp_log_count = counts.get(lead.id, 0)

    def _compute_chatberry_last_whatsapp_log(self):
        for lead in self:
            lead.chatberry_last_whatsapp_log_id = self.env["chatberry.whatsapp.message.log"].search(
                [("lead_id", "=", lead.id)],
                order="create_date desc, id desc",
                limit=1,
            )
            lead.chatberry_last_whatsapp_status = lead.chatberry_last_whatsapp_log_id.status

    def action_open_chatberry_whatsapp_logs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "WhatsApp Logs",
            "res_model": "chatberry.whatsapp.message.log",
            "view_mode": "list,form",
            "domain": [("lead_id", "=", self.id)],
            "context": {"default_lead_id": self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        return leads

    def write(self, vals):
        old_stage_by_id = {}
        old_type_by_id = {}
        should_track = not self.env.context.get("chatberry_skip_crm_automation")
        if should_track and "stage_id" in vals:
            old_stage_by_id = {lead.id: lead.stage_id for lead in self}
        if should_track and "type" in vals:
            old_type_by_id = {lead.id: lead.type for lead in self}

        result = super().write(vals)

        if old_stage_by_id:
            converted_ids = {
                lead.id for lead in self
                if old_type_by_id.get(lead.id) == "lead" and lead.type == "opportunity"
            }
            stage_change_leads = self.filtered(lambda lead: lead.id not in converted_ids)
            if stage_change_leads:
                self.env["chatberry.crm.stage.automation"].sudo()._queue_for_stage_changes(
                    stage_change_leads,
                    {lead.id: old_stage_by_id[lead.id] for lead in stage_change_leads.ids},
                )
        if old_type_by_id:
            converted_leads = self.filtered(
                lambda lead: old_type_by_id.get(lead.id) == "lead" and lead.type == "opportunity"
            )
            if converted_leads:
                self.env["chatberry.crm.stage.automation"].sudo()._queue_for_conversions(converted_leads)
        return result
