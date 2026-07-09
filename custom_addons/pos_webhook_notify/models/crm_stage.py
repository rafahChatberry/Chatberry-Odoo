from odoo import fields, models


class CrmStage(models.Model):
    _inherit = "crm.stage"

    chatberry_automation_ids = fields.One2many(
        "chatberry.crm.stage.automation",
        "to_stage_id",
        string="Chatberry WhatsApp Automations",
    )
    chatberry_automation_count = fields.Integer(compute="_compute_chatberry_automation_count")

    def _compute_chatberry_automation_count(self):
        grouped = self.env["chatberry.crm.stage.automation"].read_group(
            [("to_stage_id", "in", self.ids)],
            ["to_stage_id"],
            ["to_stage_id"],
        )
        counts = {row["to_stage_id"][0]: row["to_stage_id_count"] for row in grouped}
        for stage in self:
            stage.chatberry_automation_count = counts.get(stage.id, 0)
