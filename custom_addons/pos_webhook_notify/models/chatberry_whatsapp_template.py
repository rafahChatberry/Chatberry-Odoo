from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ChatberryWhatsappTemplate(models.Model):
    _name = "chatberry.whatsapp.template"
    _description = "Chatberry WhatsApp Template"
    _order = "name"

    name = fields.Char(required=True)
    whatsapp_template_name = fields.Char(string="WhatsApp Template Name", required=True)
    language_code = fields.Char(default="en", required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    header_media_type = fields.Selection([
        ("none", "None"),
        ("image", "Image"),
        ("video", "Video"),
        ("document", "Document"),
    ], default="none", required=True)
    header_media_source = fields.Selection([
        ("none", "None"),
        ("url", "URL"),
        ("attachment", "Odoo Attachment"),
        ("field", "Lead Field"),
    ], default="none", required=True)
    header_media_url = fields.Char()
    header_attachment_id = fields.Many2one("ir.attachment", string="Header Attachment")
    header_field_path = fields.Char(help="Example: partner_id.image_url or x_header_document_url")

    variable_ids = fields.One2many("chatberry.whatsapp.template.variable", "template_id", string="Variables")
    button_ids = fields.One2many("chatberry.whatsapp.template.button", "template_id", string="Buttons")
    crm_automation_ids = fields.One2many("chatberry.crm.stage.automation", "template_id")

    _sql_constraints = [
        ("template_name_language_company_unique",
         "unique(whatsapp_template_name, language_code, company_id)",
         "The WhatsApp template name must be unique per language and company."),
    ]

    @api.constrains("header_media_type", "header_media_source", "header_media_url", "header_attachment_id", "header_field_path")
    def _check_header_media_config(self):
        for template in self:
            if template.header_media_type == "none" and template.header_media_source != "none":
                raise ValidationError("Header source must be None when header media type is None.")
            if template.header_media_type != "none" and template.header_media_source == "none":
                raise ValidationError("Select a header media source.")
            if template.header_media_source == "url" and not template.header_media_url:
                raise ValidationError("Header media URL is required.")
            if template.header_media_source == "attachment" and not template.header_attachment_id:
                raise ValidationError("Header attachment is required.")
            if template.header_media_source == "field" and not template.header_field_path:
                raise ValidationError("Header field path is required.")


class ChatberryWhatsappTemplateVariable(models.Model):
    _name = "chatberry.whatsapp.template.variable"
    _description = "Chatberry WhatsApp Template Variable"
    _order = "component_type, position, id"

    name = fields.Char(required=True)
    template_id = fields.Many2one("chatberry.whatsapp.template", ondelete="cascade")
    button_id = fields.Many2one("chatberry.whatsapp.template.button", ondelete="cascade")
    component_type = fields.Selection([
        ("header", "Header"),
        ("body", "Body"),
        ("button", "Button"),
    ], required=True, default="body")
    position = fields.Integer(default=1, required=True)
    value_type = fields.Selection([
        ("field_path", "Lead Field Path"),
        ("static", "Static Text"),
    ], default="field_path", required=True)
    field_path = fields.Char(help="Example: partner_id.name, contact_name, stage_id.name")
    static_value = fields.Char()
    fallback_value = fields.Char()
    required = fields.Boolean(default=False)

    @api.constrains("component_type", "button_id")
    def _check_button_component(self):
        for variable in self:
            if variable.component_type == "button" and not variable.button_id:
                raise ValidationError("Button variables must be linked to a button.")
            if variable.component_type != "button" and variable.button_id:
                raise ValidationError("Only button variables can be linked to a button.")
            if variable.component_type != "button" and not variable.template_id:
                raise ValidationError("Header and body variables must be linked to a template.")
            if variable.component_type == "button" and variable.template_id and variable.template_id != variable.button_id.template_id:
                raise ValidationError("Button variable template must match the button template.")

    @api.constrains("value_type", "field_path", "static_value")
    def _check_value_source(self):
        for variable in self:
            if variable.value_type == "field_path" and not variable.field_path:
                raise ValidationError("Field path is required for field-based variables.")
            if variable.value_type == "static" and not variable.static_value:
                raise ValidationError("Static text is required for static variables.")


class ChatberryWhatsappTemplateButton(models.Model):
    _name = "chatberry.whatsapp.template.button"
    _description = "Chatberry WhatsApp Template Button"
    _order = "button_index, id"

    name = fields.Char(required=True)
    template_id = fields.Many2one("chatberry.whatsapp.template", required=True, ondelete="cascade")
    button_index = fields.Integer(default=0, required=True)
    button_type = fields.Selection([
        ("url", "URL"),
        ("quick_reply", "Quick Reply"),
    ], default="url", required=True)
    variable_ids = fields.One2many("chatberry.whatsapp.template.variable", "button_id", string="Variables")
