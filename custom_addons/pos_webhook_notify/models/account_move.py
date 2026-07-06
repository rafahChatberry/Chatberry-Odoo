import json
import logging
import requests
import threading
import base64
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = "account.move"

    whatsapp_sent = fields.Boolean(
        string="WhatsApp Sent", 
        default=False, 
        copy=False,
        help="Indicates if invoice was sent via WhatsApp"
    )
    whatsapp_last_error = fields.Char(
        string="WhatsApp Error",
        readonly=True, 
        copy=False,
        help="Last error message from WhatsApp sending attempt"
    )
    cloudinary_pdf_url = fields.Char(
        string="Cloudinary PDF URL", 
        readonly=True, 
        copy=False,
        help="Public URL of the invoice PDF on Cloudinary"
    )

    def _generate_sales_invoice_pdf(self):
        """Generate the invoice PDF for regular sales invoices"""
        self.ensure_one()
        _logger.info("📄 [SALES-PDF] Generating PDF for invoice: %s", self.name)
        
        try:
            pdf_content = None
            report_used = None
            
            IrActionsReport = self.env['ir.actions.report']
            
            report_names = [
                'account.report_invoice_with_payments',
                'account.report_invoice',
                'account.account_invoices',
            ]
            
            _logger.info("📄 [SALES-PDF] Trying %d report templates", len(report_names))
            
            for report_name in report_names:
                try:
                    _logger.info("📄 [SALES-PDF] Attempting report: %s", report_name)
                    
                    result = IrActionsReport._render_qweb_pdf(report_name, self.ids)
                    
                    if isinstance(result, tuple):
                        pdf_bytes = result[0]
                    else:
                        pdf_bytes = result
                    
                    if not isinstance(pdf_bytes, bytes):
                        _logger.warning("📄 [SALES-PDF] Report %s: not bytes (type=%s)", 
                                      report_name, type(pdf_bytes))
                        continue
                    
                    if len(pdf_bytes) == 0:
                        _logger.warning("📄 [SALES-PDF] Report %s: empty", report_name)
                        continue
                    
                    if pdf_bytes[:4] != b'%PDF':
                        _logger.warning("📄 [SALES-PDF] Report %s: not PDF", report_name)
                        continue
                    
                    pdf_content = pdf_bytes
                    report_used = report_name
                    _logger.info("✅ [SALES-PDF] SUCCESS with report: %s", report_name)
                    break
                    
                except Exception as e:
                    _logger.warning("📄 [SALES-PDF] Report %s failed: %s", report_name, str(e))
                    continue
            
            if not pdf_content:
                _logger.error("❌ [SALES-PDF] Failed to generate PDF - no valid content")
                return None, None
            
            filename = f"{self.name.replace('/', '_')}.pdf"
            
            _logger.info("✅ [SALES-PDF] PDF generated successfully!")
            _logger.info("📄 [SALES-PDF] Report used: %s", report_used)
            _logger.info("📄 [SALES-PDF] Filename: %s", filename)
            _logger.info("📄 [SALES-PDF] Size: %d bytes", len(pdf_content))
            
            return pdf_content, filename
            
        except Exception as e:
            _logger.exception("❌ [SALES-PDF] Failed to generate PDF for %s: %s", self.name, str(e))
            return None, None

    def _upload_to_cloudinary(self, pdf_content, filename, cloud_name, api_key, api_secret):
        """Upload PDF to Cloudinary via HTTP and return the public URL (no cloudinary SDK)."""
        _logger.info("☁️ [CLOUDINARY:HTTP] Uploading PDF: %s", filename)

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
            folder_path = f"invoices/{datetime.now().strftime('%Y/%m')}"
            timestamp = int(time.time())

            # Parameters to sign (exclude 'file')
            # Note: sign only keys that are set; order them lexicographically.
            params_to_sign = {
                "folder": folder_path,
                "invalidate": "true",
                "overwrite": "true",
                "public_id": filename,
                "timestamp": str(timestamp),
            }

            # Create signature: sha1 of "<key>=<value>&...<last>=<value><api_secret>"
            # Keys must be sorted alphabetically.
            to_sign = "&".join(f"{k}={v}" for k, v in sorted(params_to_sign.items()))
            signature = hashlib.sha1((to_sign + api_secret).encode("utf-8")).hexdigest()

            # Form data (include api_key and signature)
            data = {
                **params_to_sign,
                "api_key": api_key,
                "signature": signature,
            }

            # File payload
            files = {
                "file": (filename, pdf_content, "application/pdf"),
            }

            # Execute request
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

    # @staticmethod
    # def _format_phone_number_static(phone, country_code="92"):
    #     """Format phone number to international format"""
    #     if not phone:
    #         return None
        
    #     phone = str(phone).replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace(".", "")
        
    #     if phone.startswith("+"):
    #         return phone
    #     if phone.startswith("00"):
    #         return "+" + phone[2:]
    #     if phone.startswith(country_code):
    #         return "+" + phone
    #     if phone.startswith("0"):
    #         return "+" + country_code + phone[1:]
        
    #     return "+" + country_code + phone

    def _send_whatsapp_template(self, url, template_name, language_code, pdf_url, 
                               body_params, phone, auth_token):
        """Send WhatsApp template message with PDF document"""
        def _send():
            import time
            time.sleep(0.5)
            
            _logger.info("📱 [WHATSAPP-SALES] Sending template message")
            
            try:
                if not phone:
                    _logger.error("❌ [WHATSAPP-SALES] No phone number provided!")
                    return
                
                # formatted_phone = AccountMove._format_phone_number_static(phone)
                
                # if not formatted_phone:
                #     _logger.error("❌ [WHATSAPP-SALES] Invalid phone number format!")
                #     return
                
                # _logger.info("📱 [WHATSAPP-SALES] Sending to phone: %s", formatted_phone)
                
                components = []
                
                # Add PDF document header
                if pdf_url:
                    components.append({
                        "type": "header",
                        "parameters": [{
                            "type": "document",
                            "document": {"link": pdf_url}
                        }]
                    })
                
                # Add body parameters (e.g., customer name)
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
                
                _logger.info("📱 [WHATSAPP-SALES] Request payload: %s", json.dumps(payload, indent=2))
                
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                
                _logger.info("📱 [WHATSAPP-SALES] Response status: %s", resp.status_code)
                _logger.info("📱 [WHATSAPP-SALES] Response body: %s", resp.text[:500])
                
                resp.raise_for_status()
                
                _logger.info("✅ [WHATSAPP-SALES] SUCCESS!")
                
            except Exception as e:
                _logger.exception("❌ [WHATSAPP-SALES] FAILED: %s", str(e)[:250])
        
        thread = threading.Thread(target=_send)
        thread.daemon = True
        thread.start()

    def _send_sales_invoice_whatsapp(self):
        """Send WhatsApp notification when sales invoice is posted"""
        _logger.info("🟢 [SALES-INVOICE] _send_sales_invoice_whatsapp() CALLED!")
        
        Param = self.env["ir.config_parameter"].sudo()
        
        # ========================================
        # CHECK IF SALES MODULE IS ENABLED
        # ========================================
        sales_enabled = Param.get_param("pos_webhook_notify.enable_sales", "True") == "True"
        
        if not sales_enabled:
            _logger.info("🔴 [SALES-INVOICE] Sales module is DISABLED in settings. Skipping.")
            return
        
        whatsapp_url = Param.get_param("pos_webhook_notify.whatsapp_url")
        whatsapp_auth = Param.get_param("pos_webhook_notify.whatsapp_auth")
        template_name = Param.get_param("pos_webhook_notify.template_name", "payment_confirmation_2")
        language_code = Param.get_param("pos_webhook_notify.language_code", "en")
        
        cloud_name = Param.get_param("pos_webhook_notify.cloudinary_cloud_name")
        api_key = Param.get_param("pos_webhook_notify.cloudinary_api_key")
        api_secret = Param.get_param("pos_webhook_notify.cloudinary_api_secret")

        if not whatsapp_url:
            _logger.warning("🔴 [SALES-INVOICE] WhatsApp URL not configured! Skipping")
            return

        for invoice in self:
            _logger.info("🔍 [SALES-INVOICE] Checking invoice %s (state=%s, type=%s)", 
                        invoice.name, invoice.state, invoice.move_type)
            
            # Only process posted customer invoices
            if invoice.state != "posted":
                _logger.info("⏭️ [SALES-INVOICE] Skipping %s (state=%s)", invoice.name, invoice.state)
                continue
            
            if invoice.move_type != "out_invoice":
                _logger.info("⏭️ [SALES-INVOICE] Skipping %s (type=%s)", invoice.name, invoice.move_type)
                continue
            
            # Skip if already sent
            if invoice.whatsapp_sent:
                _logger.info("⏭️ [SALES-INVOICE] Already sent for %s", invoice.name)
                continue
            
            # Check for phone number
            phone = invoice.partner_id.mobile or invoice.partner_id.phone
            
            if not phone:
                _logger.warning("⚠️ [SALES-INVOICE] No phone number for invoice %s", invoice.name)
                try:
                    invoice.write({"whatsapp_last_error": "No phone number"})
                    self.env.cr.commit()
                except:
                    pass
                continue
            
            # Check Cloudinary configuration
            if not all([cloud_name, api_key, api_secret]):
                _logger.error("❌ [SALES-INVOICE] Cloudinary not configured!")
                try:
                    invoice.write({"whatsapp_last_error": "Cloudinary not configured"})
                    self.env.cr.commit()
                except:
                    pass
                continue
            
            # Generate PDF
            pdf_result = invoice._generate_sales_invoice_pdf()
            
            if not pdf_result[0]:
                _logger.error("❌ [SALES-INVOICE] PDF generation failed for %s", invoice.name)
                try:
                    invoice.write({"whatsapp_last_error": "PDF generation failed"})
                    self.env.cr.commit()
                except:
                    pass
                continue
            
            pdf_content, filename = pdf_result
            
            # Upload to Cloudinary
            pdf_url = invoice._upload_to_cloudinary(
                pdf_content, filename, cloud_name, api_key, api_secret
            )
            
            if not pdf_url:
                _logger.error("❌ [SALES-INVOICE] Cloudinary upload failed for %s", invoice.name)
                try:
                    invoice.write({"whatsapp_last_error": "Cloudinary upload failed"})
                    self.env.cr.commit()
                except:
                    pass
                continue
            
            # Save URL and mark as sent
            try:
                invoice.write({
                    "cloudinary_pdf_url": pdf_url,
                    "whatsapp_sent": True,
                    "whatsapp_last_error": False
                })
                self.env.cr.commit()
            except Exception as e:
                _logger.error("❌ [SALES-INVOICE] Could not mark as sent: %s", e)
            
            # Prepare WhatsApp message
            customer_name = invoice.partner_id.name or "Customer"
            body_params = [customer_name]
            
            token = whatsapp_auth.replace("Bearer ", "").strip() if whatsapp_auth else ""
            
            # Send WhatsApp message
            invoice._send_whatsapp_template(
                whatsapp_url, template_name, language_code, pdf_url,
                body_params, phone, token
            )

    def action_post(self):
        """Override action_post to trigger WhatsApp sending when invoice is confirmed"""
        res = super().action_post()
        
        # Check if Sales module is enabled
        Param = self.env["ir.config_parameter"].sudo()
        sales_enabled = Param.get_param("pos_webhook_notify.enable_sales", "True") == "True"
        
        if not sales_enabled:
            _logger.info("🔴 [SALES-INVOICE] Sales module is DISABLED. Skipping WhatsApp.")
            return res
        
        # Filter for customer invoices that should trigger WhatsApp
        invoices_to_notify = self.filtered(
            lambda inv: inv.move_type == 'out_invoice' and 
                       inv.state == 'posted' and 
                       not inv.whatsapp_sent
        )
        
        if invoices_to_notify:
            _logger.info("📨 [SALES-INVOICE] Triggering WhatsApp for %d invoice(s)", len(invoices_to_notify))
            # Small delay to ensure invoice is fully posted
            import time
            time.sleep(0.3)
            invoices_to_notify._send_sales_invoice_whatsapp()
        
        return res