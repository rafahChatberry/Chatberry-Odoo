import base64
import hashlib
import json
import logging
import re
import time
from datetime import date, datetime

import requests

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

FIELD_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


class ChatberryWhatsappVariableResolver(models.AbstractModel):
    _name = "chatberry.whatsapp.variable.resolver"
    _description = "Chatberry WhatsApp Variable Resolver"

    def resolve_path(self, record, field_path):
        if not field_path or not FIELD_PATH_RE.match(field_path):
            raise UserError("Invalid field path: %s" % (field_path or ""))

        value = record
        for field_name in field_path.split("."):
            if not value:
                return False
            if field_name not in value._fields:
                raise UserError("Field '%s' does not exist on model '%s'." % (field_name, value._name))
            value = value[field_name]
            if hasattr(value, "_name") and len(value) > 1:
                value = value[:1]
        return value

    def stringify_value(self, value):
        if value is False or value is None:
            return ""
        if hasattr(value, "_name"):
            return value.display_name if value else ""
        if isinstance(value, datetime):
            return fields.Datetime.to_string(value)
        if isinstance(value, date):
            return fields.Date.to_string(value)
        return str(value)

    def resolve_template_variable(self, variable, record):
        if variable.value_type == "static":
            value = variable.static_value or ""
        else:
            value = self.stringify_value(self.resolve_path(record, variable.field_path))

        if not value and variable.fallback_value:
            value = variable.fallback_value
        if not value and variable.required:
            raise UserError("Required variable '%s' resolved to an empty value." % variable.name)
        return value or ""


class ChatberryWhatsappMediaService(models.AbstractModel):
    _name = "chatberry.whatsapp.media.service"
    _description = "Chatberry WhatsApp Media Service"

    def get_header_media_url(self, template, record):
        if template.header_media_type == "none" or template.header_media_source == "none":
            return False
        if template.header_media_source == "url":
            return template.header_media_url
        if template.header_media_source == "field":
            resolver = self.env["chatberry.whatsapp.variable.resolver"]
            return resolver.stringify_value(resolver.resolve_path(record, template.header_field_path))
        if template.header_media_source == "attachment":
            return self._upload_attachment_to_cloudinary(template.header_attachment_id)
        return False

    def _upload_attachment_to_cloudinary(self, attachment):
        if not attachment:
            raise UserError("Header attachment is not configured.")

        Param = self.env["ir.config_parameter"].sudo()
        cloud_name = Param.get_param("pos_webhook_notify.cloudinary_cloud_name")
        api_key = Param.get_param("pos_webhook_notify.cloudinary_api_key")
        api_secret = Param.get_param("pos_webhook_notify.cloudinary_api_secret")
        if not all([cloud_name, api_key, api_secret]):
            raise UserError("Cloudinary is not configured.")

        content = base64.b64decode(attachment.datas or b"")
        if not content:
            raise UserError("Header attachment is empty.")

        upload_url = "https://api.cloudinary.com/v1_1/%s/raw/upload" % cloud_name
        folder_path = "chatberry_crm/%s" % datetime.now().strftime("%Y/%m")
        timestamp = int(time.time())
        public_id = attachment.name or ("crm_media_%s" % timestamp)
        params_to_sign = {
            "folder": folder_path,
            "invalidate": "true",
            "overwrite": "true",
            "public_id": public_id,
            "timestamp": str(timestamp),
        }
        to_sign = "&".join("%s=%s" % (k, v) for k, v in sorted(params_to_sign.items()))
        signature = hashlib.sha1((to_sign + api_secret).encode("utf-8")).hexdigest()
        data = {**params_to_sign, "api_key": api_key, "signature": signature}
        files = {"file": (public_id, content, attachment.mimetype or "application/octet-stream")}
        resp = requests.post(upload_url, data=data, files=files, timeout=60)
        _logger.info("[CHATBERRY:CRM:MEDIA] Cloudinary status=%s body=%s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        info = resp.json()
        url = info.get("secure_url") or info.get("url")
        if not url:
            raise UserError("Cloudinary upload succeeded but did not return a URL.")
        return url


class ChatberryWhatsappPayloadBuilder(models.AbstractModel):
    _name = "chatberry.whatsapp.payload.builder"
    _description = "Chatberry WhatsApp Payload Builder"

    def build_payload(self, template, record, phone):
        resolver = self.env["chatberry.whatsapp.variable.resolver"]
        media_service = self.env["chatberry.whatsapp.media.service"]
        components = []

        header_params = []
        media_url = media_service.get_header_media_url(template, record)
        if media_url:
            media_type = template.header_media_type
            header_params.append({
                "type": media_type,
                media_type: {"link": media_url},
            })

        for variable in template.variable_ids.filtered(lambda item: item.component_type == "header").sorted("position"):
            header_params.append({"type": "text", "text": resolver.resolve_template_variable(variable, record)})
        if header_params:
            components.append({"type": "header", "parameters": header_params})

        body_params = [
            {"type": "text", "text": resolver.resolve_template_variable(variable, record)}
            for variable in template.variable_ids.filtered(lambda item: item.component_type == "body").sorted("position")
        ]
        if body_params:
            components.append({"type": "body", "parameters": body_params})

        for button in template.button_ids.sorted("button_index"):
            button_params = [
                {"type": "text", "text": resolver.resolve_template_variable(variable, record)}
                for variable in button.variable_ids.sorted("position")
            ]
            if button_params:
                components.append({
                    "type": "button",
                    "sub_type": button.button_type,
                    "index": str(button.button_index),
                    "parameters": button_params,
                })

        return {
            "phone": phone,
            "template": {
                "name": template.whatsapp_template_name,
                "language": {"code": template.language_code},
                "components": components,
            },
        }


class ChatberryWhatsappSender(models.AbstractModel):
    _name = "chatberry.whatsapp.sender"
    _description = "Chatberry WhatsApp Sender"

    def send_payload(self, payload):
        Param = self.env["ir.config_parameter"].sudo()
        url = Param.get_param("pos_webhook_notify.whatsapp_url")
        auth_token = Param.get_param("pos_webhook_notify.whatsapp_auth")
        if not url:
            raise UserError("WhatsApp API URL is not configured.")

        headers = {"Content-Type": "application/json"}
        if auth_token:
            clean_token = auth_token.replace("Bearer ", "").strip()
            headers["Authorization"] = "Bearer %s" % clean_token

        _logger.info("[CHATBERRY:CRM:SEND] Payload: %s", json.dumps(payload, indent=2))
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        _logger.info("[CHATBERRY:CRM:SEND] Status=%s body=%s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        return {
            "status_code": resp.status_code,
            "body": resp.text,
        }
