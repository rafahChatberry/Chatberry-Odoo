import json
import logging
import requests
import threading
import base64
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = "pos.order"

    webhook_sent = fields.Boolean(default=False, copy=False)
    webhook_last_error = fields.Char(readonly=True, copy=False)
    whatsapp_sent = fields.Boolean(default=False, copy=False)
    whatsapp_last_error = fields.Char(readonly=True, copy=False)
    cloudinary_pdf_url = fields.Char(string="Cloudinary PDF URL", readonly=True, copy=False)

    def _payload_for_webhook(self):
        """Build JSON payload for webhook"""
        _logger.info("📵 [WEBHOOK] Building payload for order: %s", self.name)
        self.ensure_one()
        lines = [{
            "product": l.product_id.display_name,
            "qty": l.qty,
            "price_unit": l.price_unit,
            "subtotal": l.price_subtotal,
            "tax": l.price_subtotal_incl - l.price_subtotal,
        } for l in self.lines]

        payments = [{
            "method": p.payment_method_id.display_name,
            "amount": p.amount,
            "date": p.payment_date.isoformat() if p.payment_date else None,
        } for p in self.payment_ids]

        payload = {
            "order_name": self.name,
            "pos_reference": self.pos_reference,
            "state": self.state,
            "session_id": self.session_id.id,
            "currency": self.pricelist_id.currency_id.name if self.pricelist_id.currency_id else self.currency_id.name,
            "amount_total": self.amount_total,
            "amount_tax": self.amount_tax,
            "amount_paid": self.amount_paid,
            "amount_return": self.amount_return,
            "date_order": self.date_order.isoformat() if self.date_order else None,
            "partner": {
                "id": self.partner_id.id or None,
                "name": self.partner_id.name or None,
                "phone": self.partner_id.phone or None,
                "mobile": self.partner_id.mobile or None,
                "email": self.partner_id.email or None,
            },
            "lines": lines,
            "payments": payments,
        }
        _logger.info("📵 [WEBHOOK] Payload built successfully for %s", self.name)
        return payload

    def _generate_receipt_pdf(self):
        """
        Generate POS receipt PDF using custom template that matches invoice format
        """
        self.ensure_one()
        _logger.info("🧾 [RECEIPT] Generating POS receipt PDF for: %s", self.name)
        
        try:
            # Small delay to ensure order is fully created
            import time
            time.sleep(0.5)
            
            # Force cache refresh
            self.invalidate_recordset()
            
            IrActionsReport = self.env['ir.actions.report']
            
            # ========================================
            # Use our custom POS receipt template
            # ========================================
            custom_report_name = 'pos_webhook_notify.report_pos_receipt_custom'
            
            _logger.info("🧾 [RECEIPT] Using custom receipt template: %s", custom_report_name)
            
            try:
                result = IrActionsReport._render_qweb_pdf(custom_report_name, self.ids)
                
                if isinstance(result, tuple):
                    pdf_bytes = result[0]
                else:
                    pdf_bytes = result
                
                # Validate
                if not isinstance(pdf_bytes, bytes):
                    _logger.error("🧾 [RECEIPT] Custom report: not bytes (type=%s)", type(pdf_bytes))
                    return None, None
                
                if len(pdf_bytes) == 0:
                    _logger.error("🧾 [RECEIPT] Custom report: empty")
                    return None, None
                
                if pdf_bytes[:4] != b'%PDF':
                    _logger.error("🧾 [RECEIPT] Custom report: not PDF")
                    return None, None
                
                # SUCCESS!
                filename = f"{self.name.replace('/', '_')}_receipt.pdf"
                _logger.info("✅ [RECEIPT] SUCCESS with custom template!")
                _logger.info("🧾 [RECEIPT] Filename: %s", filename)
                _logger.info("🧾 [RECEIPT] Size: %d bytes", len(pdf_bytes))
                
                return pdf_bytes, filename
                
            except Exception as e:
                _logger.exception("❌ [RECEIPT] Custom template failed: %s", str(e))
                
                # ========================================
                # FALLBACK: Create invoice automatically
                # ========================================
                _logger.info("⚠️ [RECEIPT] Falling back to invoice creation...")
                
                invoice = self.account_move
                
                if not invoice:
                    invoice = self.env['account.move'].search([
                        ('pos_order_ids', 'in', self.ids),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                
                if not invoice:
                    try:
                        self.action_pos_order_invoice()
                        self.invalidate_recordset()
                        invoice = self.account_move
                        
                        if not invoice:
                            invoice = self.env['account.move'].search([
                                ('pos_order_ids', 'in', self.ids),
                                ('move_type', '=', 'out_invoice')
                            ], limit=1, order='create_date desc')
                        
                        if invoice:
                            _logger.info("✅ [RECEIPT] Invoice created: %s", invoice.name)
                    except Exception as inv_err:
                        _logger.exception("❌ [RECEIPT] Invoice creation failed: %s", str(inv_err))
                        return None, None
                
                if invoice:
                    invoice_report_names = [
                        'account.report_invoice_with_payments',
                        'account.report_invoice',
                        'account.account_invoices',
                    ]
                    
                    for report_name in invoice_report_names:
                        try:
                            result = IrActionsReport._render_qweb_pdf(report_name, invoice.ids)
                            
                            if isinstance(result, tuple):
                                pdf_bytes = result[0]
                            else:
                                pdf_bytes = result
                            
                            if isinstance(pdf_bytes, bytes) and len(pdf_bytes) > 0 and pdf_bytes[:4] == b'%PDF':
                                filename = f"{self.name.replace('/', '_')}_invoice.pdf"
                                _logger.info("✅ [RECEIPT] Fallback success with: %s", report_name)
                                return pdf_bytes, filename
                                
                        except Exception as rep_err:
                            _logger.warning("🧾 [RECEIPT] Report %s failed: %s", report_name, str(rep_err))
                            continue
                
                return None, None
            
        except Exception as e:
            _logger.exception("❌ [RECEIPT] Failed to generate PDF for %s: %s", self.name, str(e))
            return None, None

    def _upload_to_cloudinary(self, pdf_content, filename, cloud_name, api_key, api_secret):
        """Upload PDF to Cloudinary via HTTP and return the public URL (no cloudinary SDK)."""
        _logger.info("☁️ [CLOUDINARY:HTTP] Uploading POS PDF: %s", filename)

        try:
            import hashlib
            import time
            from datetime import datetime

            # Validate input
            if not isinstance(pdf_content, bytes) or not pdf_content:
                _logger.error("❌ [CLOUDINARY:HTTP] pdf_content must be non-empty bytes (got %s)", type(pdf_content))
                return None

            # Endpoint for raw upload
            upload_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/raw/upload"

            # Build options
            folder_path = f"pos_receipts/{datetime.now().strftime('%Y/%m')}"
            timestamp = int(time.time())

            # Parameters to sign (exclude 'file')
            params_to_sign = {
                "folder": folder_path,
                "invalidate": "true",
                "overwrite": "true",
                "public_id": filename,
                "timestamp": str(timestamp),
            }

            to_sign = "&".join(f"{k}={v}" for k, v in sorted(params_to_sign.items()))
            signature = hashlib.sha1((to_sign + api_secret).encode("utf-8")).hexdigest()

            data = {
                **params_to_sign,
                "api_key": api_key,
                "signature": signature,
            }

            files = {
                "file": (filename, pdf_content, "application/pdf"),
            }

            resp = requests.post(upload_url, data=data, files=files, timeout=60)
            _logger.info("☁️ [CLOUDINARY:HTTP] Status: %s Body: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()

            info = resp.json()
            url = info.get("secure_url") or info.get("url")
            if not url:
                _logger.error("❌ [CLOUDINARY:HTTP] Upload ok but URL missing in response.")
                return None

            _logger.info("✅ [CLOUDINARY:HTTP] Uploaded successfully! URL: %s", url)
            return url

        except Exception as e:
            _logger.exception("❌ [CLOUDINARY:HTTP] Upload failed: %s", str(e))
            return None

    def _send_whatsapp_template(self, url, template_name, language_code, pdf_url, 
                               body_params, phone, auth_token):
        """Send WhatsApp template message with PDF document"""
        def _send():
            import time
            time.sleep(0.5)
            
            _logger.info("📱 [WHATSAPP-POS] Sending template message")
            
            try:
                if not phone:
                    _logger.error("❌ [WHATSAPP-POS] No phone number provided!")
                    return
                
                _logger.info("📱 [WHATSAPP-POS] Sending to phone: %s", phone)
                
                components = []
                
                if pdf_url:
                    components.append({
                        "type": "header",
                        "parameters": [{
                            "type": "document",
                            "document": {"link": pdf_url}
                        }]
                    })
                
                if body_params:
                    body_parameters = [{"type": "text", "text": str(param)} for param in body_params]
                    components.append({
                        "type": "body",
                        "parameters": body_parameters
                    })
                
                payload = {
                    "phone": phone,
                    "template": {
                        "name": template_name,
                        "language": {"code": language_code},
                        "components": components
                    }
                }
                
                headers = {"Content-Type": "application/json"}
                
                if auth_token:
                    clean_token = auth_token.replace("Bearer ", "").strip()
                    headers["Authorization"] = f"Bearer {clean_token}"
                
                _logger.info("📱 [WHATSAPP-POS] Request payload: %s", json.dumps(payload, indent=2))
                
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                
                _logger.info("📱 [WHATSAPP-POS] Response status: %s", resp.status_code)
                _logger.info("📱 [WHATSAPP-POS] Response body: %s", resp.text[:500])
                
                resp.raise_for_status()
                
                _logger.info("✅ [WHATSAPP-POS] SUCCESS!")
                
            except Exception as e:
                _logger.exception("❌ [WHATSAPP-POS] FAILED: %s", str(e)[:250])
        
        thread = threading.Thread(target=_send)
        thread.daemon = True
        thread.start()

    def _do_webhook_request(self, url, payload, headers):
        """Execute the actual HTTP request in a separate thread"""
        def _send():
            import time
            time.sleep(0.3)
            
            _logger.info("🚀 [WEBHOOK] Sending HTTP POST to %s", url)
            
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                resp.raise_for_status()
                _logger.info("✅ [WEBHOOK] SUCCESS! Response status: %s", resp.status_code)
            except Exception as e:
                _logger.exception("❌ [WEBHOOK] FAILED: %s", str(e)[:250])
        
        thread = threading.Thread(target=_send)
        thread.daemon = True
        thread.start()

    def _send_pos_webhook(self):
        """Send webhook ONCE per order when it reaches paid/invoiced state"""
        _logger.info("🟢 [POS-WEBHOOK] _send_pos_webhook() CALLED!")
        
        Param = self.env["ir.config_parameter"].sudo()
        
        # ========================================
        # CHECK IF POS MODULE IS ENABLED
        # ========================================
        pos_enabled = Param.get_param("pos_webhook_notify.enable_pos", "True") == "True"
        
        if not pos_enabled:
            _logger.info("🔴 [POS-WEBHOOK] POS module is DISABLED in settings. Skipping.")
            return
        
        url = Param.get_param("pos_webhook_notify.url")
        auth = Param.get_param("pos_webhook_notify.auth") or ""
        
        whatsapp_url = Param.get_param("pos_webhook_notify.whatsapp_url")
        whatsapp_auth = Param.get_param("pos_webhook_notify.whatsapp_auth") or auth
        template_name = Param.get_param("pos_webhook_notify.template_name", "payment_confirmation_2")
        language_code = Param.get_param("pos_webhook_notify.language_code", "en")
        
        cloud_name = Param.get_param("pos_webhook_notify.cloudinary_cloud_name")
        api_key = Param.get_param("pos_webhook_notify.cloudinary_api_key")
        api_secret = Param.get_param("pos_webhook_notify.cloudinary_api_secret")

        if not url and not whatsapp_url:
            _logger.warning("🔴 [POS-WEBHOOK] No URLs configured! Skipping")
            return

        for order in self:
            _logger.info("🔍 [POS-WEBHOOK] Checking order %s (state=%s)", order.name, order.state)
            
            if order.state not in ("paid", "invoiced"):
                _logger.info("⏭️ [POS-WEBHOOK] Skipping %s (state=%s)", order.name, order.state)
                continue
            
            # ========================================
            # JSON WEBHOOK
            # ========================================
            if url and not order.webhook_sent:
                payload = order._payload_for_webhook()
                headers = {"Content-Type": "application/json"}
                if auth:
                    headers["Authorization"] = auth
                
                try:
                    order.write({"webhook_sent": True, "webhook_last_error": False})
                    self.env.cr.commit()
                except Exception as e:
                    _logger.error("❌ [POS-WEBHOOK] Could not mark as sent: %s", e)
                    continue
                
                self._do_webhook_request(url, payload, headers)
            
            # ========================================
            # WHATSAPP TEMPLATE
            # ========================================
            if whatsapp_url and not order.whatsapp_sent:
                phone = order.partner_id.mobile or order.partner_id.phone
                
                if not phone:
                    _logger.warning("⚠️ [POS-WHATSAPP] No phone number for order %s", order.name)
                    try:
                        order.write({"whatsapp_last_error": "No phone number"})
                        self.env.cr.commit()
                    except:
                        pass
                    continue
                
                if not all([cloud_name, api_key, api_secret]):
                    _logger.error("❌ [POS-WHATSAPP] Cloudinary not configured!")
                    try:
                        order.write({"whatsapp_last_error": "Cloudinary not configured"})
                        self.env.cr.commit()
                    except:
                        pass
                    continue
                
                # ========================================
                # GENERATE POS RECEIPT PDF (ALWAYS)
                # ========================================
                _logger.info("🧾 [POS-WHATSAPP] Generating receipt PDF (ignoring invoice checkbox)...")
                pdf_result = order._generate_receipt_pdf()
                
                if not pdf_result[0]:
                    _logger.error("❌ [POS-WHATSAPP] Receipt PDF generation failed for %s", order.name)
                    try:
                        order.write({"whatsapp_last_error": "Receipt PDF generation failed"})
                        self.env.cr.commit()
                    except:
                        pass
                    continue
                
                pdf_content, filename = pdf_result
                
                # Upload to Cloudinary
                pdf_url = order._upload_to_cloudinary(
                    pdf_content, filename, cloud_name, api_key, api_secret
                )
                
                if not pdf_url:
                    _logger.error("❌ [POS-WHATSAPP] Cloudinary upload failed for %s", order.name)
                    try:
                        order.write({"whatsapp_last_error": "Cloudinary upload failed"})
                        self.env.cr.commit()
                    except:
                        pass
                    continue
                
                # Save URL
                try:
                    order.write({"cloudinary_pdf_url": pdf_url})
                    self.env.cr.commit()
                except:
                    pass
                
                customer_name = order.partner_id.name or "Customer"
                body_params = [customer_name]
                
                # Mark as sent
                try:
                    order.write({"whatsapp_sent": True, "whatsapp_last_error": False})
                    self.env.cr.commit()
                except Exception as e:
                    _logger.error("❌ [POS-WHATSAPP] Could not mark as sent: %s", e)
                
                token = whatsapp_auth.replace("Bearer ", "").strip() if whatsapp_auth else ""
                
                order._send_whatsapp_template(
                    whatsapp_url, template_name, language_code, pdf_url,
                    body_params, phone, token
                )

    @api.model
    def sync_from_ui(self, orders):
        """Override POS sync method to trigger webhook"""
        result = super().sync_from_ui(orders)
        
        # Check if POS module is enabled
        Param = self.env["ir.config_parameter"].sudo()
        pos_enabled = Param.get_param("pos_webhook_notify.enable_pos", "True") == "True"
        
        if not pos_enabled:
            _logger.info("🔴 [POS-SYNC] POS module is DISABLED. Skipping webhook.")
            return result
        
        if result and 'pos.order' in result:
            order_data = result['pos.order']
            order_ids = [o['id'] if isinstance(o, dict) else o for o in order_data]
            synced_orders = self.browse(order_ids)
            
            for order in synced_orders:
                url = Param.get_param("pos_webhook_notify.url")
                whatsapp_url = Param.get_param("pos_webhook_notify.whatsapp_url")
                
                needs_webhook = url and order.state in ("paid", "invoiced") and not order.webhook_sent
                needs_whatsapp = whatsapp_url and order.state in ("paid", "invoiced") and not order.whatsapp_sent
                
                if needs_webhook or needs_whatsapp:
                    import time
                    time.sleep(0.2)
                    order.invalidate_recordset()
                    order._send_pos_webhook()
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Create orders"""
        orders = super().create(vals_list)
        return orders

    def write(self, vals):
        """Trigger webhook when state changes"""
        res = super().write(vals)
        
        # Check if POS module is enabled
        Param = self.env["ir.config_parameter"].sudo()
        pos_enabled = Param.get_param("pos_webhook_notify.enable_pos", "True") == "True"
        
        if not pos_enabled:
            return res
        
        if "state" in vals and vals["state"] in ("paid", "invoiced"):
            if not self.pos_reference:
                self._send_pos_webhook()
        
        return res