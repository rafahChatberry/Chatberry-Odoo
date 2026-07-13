import json
import logging
import requests
import threading
import base64
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = "sale.order"

    whatsapp_sent_website = fields.Boolean(
        string="Website WhatsApp Sent", 
        default=False, 
        copy=False,
        help="Indicates if website order confirmation was sent via WhatsApp"
    )
    whatsapp_last_error_website = fields.Char(
        string="Website WhatsApp Error",
        readonly=True, 
        copy=False,
        help="Last error message from WhatsApp sending attempt for website order"
    )
    cloudinary_pdf_url_website = fields.Char(
        string="Website Order Cloudinary PDF URL", 
        readonly=True, 
        copy=False,
        help="Public URL of the website order PDF on Cloudinary"
    )

    # def _format_phone_for_whatsapp(self, phone, partner=None):
    #     """
    #     Format phone number for WhatsApp - EXPLICIT COUNTRY HANDLING
    #     Supports: Pakistan (+92), Oman (+968), Egypt (+20), Saudi Arabia (+966)
    #     """
    #     if not phone:
    #         return None
        
    #     # Clean the phone number - remove all spaces, dashes, brackets, dots
    #     phone = str(phone).strip()
    #     phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace(".", "").replace("+", "")
        
    #     _logger.info("📞 [PHONE] Original (cleaned): %s", phone)
        
    #     # Remove leading zeros or 00
    #     while phone.startswith("0") and len(phone) > 10:
    #         phone = phone[1:]
        
    #     _logger.info("📞 [PHONE] After removing leading zeros: %s", phone)
        
    #     # ============================================
    #     # PAKISTAN - Country Code: 92
    #     # ============================================
    #     # Format: 3XX XXXXXXX (10 digits after 0)
    #     # Examples: 03001234567 → +923001234567
    #     if phone.startswith("92") and len(phone) == 12:  # Already has 92
    #         formatted = "+" + phone
    #         _logger.info("✅ [PHONE-PK] Pakistan number with code: %s", formatted)
    #         return formatted
        
    #     if phone.startswith("3") and len(phone) == 10:  # Local without 0
    #         formatted = "+92" + phone
    #         _logger.info("✅ [PHONE-PK] Pakistan local format: %s", formatted)
    #         return formatted
        
    #     if phone.startswith("03") and len(phone) == 11:  # Local with 0
    #         formatted = "+92" + phone[1:]
    #         _logger.info("✅ [PHONE-PK] Pakistan format 03XX: %s", formatted)
    #         return formatted
        
    #     # ============================================
    #     # OMAN - Country Code: 968
    #     # ============================================
    #     # Format: XXXX XXXX (8 digits)
    #     # Examples: 91234567 → +96891234567
    #     if phone.startswith("968") and len(phone) == 11:  # Already has 968
    #         formatted = "+" + phone
    #         _logger.info("✅ [PHONE-OM] Oman number with code: %s", formatted)
    #         return formatted
        
    #     if len(phone) == 8 and phone[0] in ['7', '9']:  # Oman mobile starts with 7 or 9
    #         formatted = "+968" + phone
    #         _logger.info("✅ [PHONE-OM] Oman local format: %s", formatted)
    #         return formatted
        
    #     # ============================================
    #     # EGYPT - Country Code: 20
    #     # ============================================
    #     # Format: 1X XXXX XXXX (10 digits after 0)
    #     # Examples: 01012345678 → +201012345678
    #     if phone.startswith("20") and len(phone) == 12:  # Already has 20
    #         formatted = "+" + phone
    #         _logger.info("✅ [PHONE-EG] Egypt number with code: %s", formatted)
    #         return formatted
        
    #     if phone.startswith("1") and len(phone) == 10:  # Local without 0
    #         formatted = "+20" + phone
    #         _logger.info("✅ [PHONE-EG] Egypt local format: %s", formatted)
    #         return formatted
        
    #     if phone.startswith("01") and len(phone) == 11:  # Local with 0
    #         formatted = "+20" + phone[1:]
    #         _logger.info("✅ [PHONE-EG] Egypt format 01X: %s", formatted)
    #         return formatted
        
    #     # ============================================
    #     # SAUDI ARABIA - Country Code: 966
    #     # ============================================
    #     # Format: 5X XXX XXXX (9 digits after 0)
    #     # Examples: 0501234567 → +966501234567
    #     if phone.startswith("966") and len(phone) == 12:  # Already has 966
    #         formatted = "+" + phone
    #         _logger.info("✅ [PHONE-SA] Saudi number with code: %s", formatted)
    #         return formatted
        
    #     if phone.startswith("5") and len(phone) == 9:  # Local without 0
    #         formatted = "+966" + phone
    #         _logger.info("✅ [PHONE-SA] Saudi local format: %s", formatted)
    #         return formatted
        
    #     if phone.startswith("05") and len(phone) == 10:  # Local with 0
    #         formatted = "+966" + phone[1:]
    #         _logger.info("✅ [PHONE-SA] Saudi format 05X: %s", formatted)
    #         return formatted
        
    #     # ============================================
    #     # FALLBACK - Try to detect from partner country
    #     # ============================================
    #     if partner and partner.country_id:
    #         country_code = partner.country_id.phone_code
    #         country_name = partner.country_id.name
            
    #         _logger.info("📞 [PHONE] Trying partner country: %s (code: %s)", country_name, country_code)
            
    #         if country_code:
    #             # If number already starts with country code
    #             if phone.startswith(country_code):
    #                 formatted = "+" + phone
    #                 _logger.info("✅ [PHONE] Added + to existing country code: %s", formatted)
    #                 return formatted
                
    #             # Otherwise add country code
    #             formatted = "+" + country_code + phone
    #             _logger.info("✅ [PHONE] Added country code from partner: %s", formatted)
    #             return formatted
        
    #     # ============================================
    #     # LAST RESORT - Just add + if not already there
    #     # ============================================
    #     _logger.warning("⚠️ [PHONE] Could not match country pattern, returning with +: +%s", phone)
    #     return "+" + phone

    def _generate_website_order_pdf(self):
        """Generate the order PDF for website/e-commerce orders"""
        self.ensure_one()
        _logger.info("📄 [WEBSITE-PDF] Generating PDF for order: %s", self.name)
        
        try:
            pdf_content = None
            report_used = None
            
            IrActionsReport = self.env['ir.actions.report']
            
            # Try multiple sale order report templates
            report_names = [
                'sale.action_report_saleorder',
                'sale.report_saleorder',
                'sale_management.report_saleorder_pro_forma',
            ]
            
            _logger.info("📄 [WEBSITE-PDF] Trying %d report templates", len(report_names))
            
            for report_name in report_names:
                try:
                    _logger.info("📄 [WEBSITE-PDF] Attempting report: %s", report_name)
                    
                    result = IrActionsReport._render_qweb_pdf(report_name, self.ids)
                    
                    if isinstance(result, tuple):
                        pdf_bytes = result[0]
                    else:
                        pdf_bytes = result
                    
                    if not isinstance(pdf_bytes, bytes):
                        _logger.warning("📄 [WEBSITE-PDF] Report %s: not bytes (type=%s)", 
                                      report_name, type(pdf_bytes))
                        continue
                    
                    if len(pdf_bytes) == 0:
                        _logger.warning("📄 [WEBSITE-PDF] Report %s: empty", report_name)
                        continue
                    
                    if pdf_bytes[:4] != b'%PDF':
                        _logger.warning("📄 [WEBSITE-PDF] Report %s: not PDF", report_name)
                        continue
                    
                    pdf_content = pdf_bytes
                    report_used = report_name
                    _logger.info("✅ [WEBSITE-PDF] SUCCESS with report: %s", report_name)
                    break
                    
                except Exception as e:
                    _logger.warning("📄 [WEBSITE-PDF] Report %s failed: %s", report_name, str(e))
                    continue
            
            if not pdf_content:
                _logger.error("❌ [WEBSITE-PDF] Failed to generate PDF - no valid content")
                return None, None
            
            filename = f"{self.name.replace('/', '_')}_order.pdf"
            
            _logger.info("✅ [WEBSITE-PDF] PDF generated successfully!")
            _logger.info("📄 [WEBSITE-PDF] Report used: %s", report_used)
            _logger.info("📄 [WEBSITE-PDF] Filename: %s", filename)
            _logger.info("📄 [WEBSITE-PDF] Size: %d bytes", len(pdf_content))
            
            return pdf_content, filename
            
        except Exception as e:
            _logger.exception("❌ [WEBSITE-PDF] Failed to generate PDF for %s: %s", self.name, str(e))
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
            folder_path = f"website_orders/{datetime.now().strftime('%Y/%m')}"
            timestamp = int(time.time())

            # Parameters to sign (exclude 'file')
            params_to_sign = {
                "folder": folder_path,
                "invalidate": "true",
                "overwrite": "true",
                "public_id": filename,
                "timestamp": str(timestamp),
            }

            # Create signature
            to_sign = "&".join(f"{k}={v}" for k, v in sorted(params_to_sign.items()))
            signature = hashlib.sha1((to_sign + api_secret).encode("utf-8")).hexdigest()

            # Form data
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

    def _send_whatsapp_template(self, url, template_name, language_code, pdf_url, 
                               body_params, phone, auth_token):
        """Send WhatsApp template message with PDF document"""
        def _send():
            import time
            time.sleep(0.5)
            
            _logger.info("📱 [WHATSAPP-WEBSITE] Sending template message")
            _logger.info("📱 [WHATSAPP-WEBSITE] Phone: %s", phone)
            
            try:
                components = []
                
                # Add PDF as header
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
                
                _logger.info("📱 [WHATSAPP-WEBSITE] Request payload: %s", json.dumps(payload, indent=2))
                
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                
                _logger.info("📱 [WHATSAPP-WEBSITE] Response status: %s", resp.status_code)
                _logger.info("📱 [WHATSAPP-WEBSITE] Response body: %s", resp.text[:500])
                
                resp.raise_for_status()
                
                _logger.info("✅ [WHATSAPP-WEBSITE] SUCCESS!")
                
            except Exception as e:
                _logger.exception("❌ [WHATSAPP-WEBSITE] FAILED: %s", str(e)[:250])
        
        thread = threading.Thread(target=_send)
        thread.daemon = True
        thread.start()

    def _send_website_order_whatsapp(self):
        """Send WhatsApp notification when website order is confirmed/paid"""
        _logger.info("🟢 [WEBSITE-ORDER] _send_website_order_whatsapp() CALLED!")
        
        Param = self.env["ir.config_parameter"].sudo()
        
        # ========================================
        # CHECK IF SALES MODULE IS ENABLED
        # ========================================
        sales_enabled = Param.get_param("pos_webhook_notify.enable_sales", "True") == "True"
        
        if not sales_enabled:
            _logger.info("🔴 [WEBSITE-ORDER] Sales module is DISABLED in settings. Skipping.")
            return
        
        whatsapp_url = Param.get_param("pos_webhook_notify.whatsapp_url")
        whatsapp_auth = Param.get_param("pos_webhook_notify.whatsapp_auth")
        template_name = Param.get_param("pos_webhook_notify.template_name", "payment_confirmation_2")
        language_code = Param.get_param("pos_webhook_notify.language_code", "en")
        
        cloud_name = Param.get_param("pos_webhook_notify.cloudinary_cloud_name")
        api_key = Param.get_param("pos_webhook_notify.cloudinary_api_key")
        api_secret = Param.get_param("pos_webhook_notify.cloudinary_api_secret")

        if not whatsapp_url:
            _logger.warning("🔴 [WEBSITE-ORDER] WhatsApp URL not configured! Skipping")
            return

        for order in self:
            _logger.info("🔍 [WEBSITE-ORDER] Checking order %s (state=%s, website_id=%s)", 
                        order.name, order.state, order.website_id.id if order.website_id else None)
            
            # Only process confirmed website orders
            if not order.website_id:
                _logger.info("⏭️ [WEBSITE-ORDER] Skipping %s (not a website order)", order.name)
                continue
            
            if order.state not in ('sale', 'done'):
                _logger.info("⏭️ [WEBSITE-ORDER] Skipping %s (state=%s)", order.name, order.state)
                continue
            
            # Skip if already sent
            if order.whatsapp_sent_website:
                _logger.info("⏭️ [WEBSITE-ORDER] Already sent for %s", order.name)
                continue
            
            # Check for phone number - try shipping address first, then billing
            raw_phone = None
            if order.partner_shipping_id:
                raw_phone = order.partner_shipping_id.mobile or order.partner_shipping_id.phone
                _logger.info("📞 [WEBSITE-ORDER] Trying phone from shipping address: %s", raw_phone)
            
            if not raw_phone:
                raw_phone = order.partner_id.mobile or order.partner_id.phone
                _logger.info("📞 [WEBSITE-ORDER] Using phone from billing address: %s", raw_phone)
            
            if not raw_phone:
                _logger.warning("⚠️ [WEBSITE-ORDER] No phone number for order %s", order.name)
                try:
                    order.write({"whatsapp_last_error_website": "No phone number"})
                    self.env.cr.commit()
                except:
                    pass
                continue
            
            _logger.info("📞 [WEBSITE-ORDER] Raw phone from database: %s", raw_phone)
            
            # Use shipping partner for country detection if available
            # phone_partner = order.partner_shipping_id if order.partner_shipping_id else order.partner_id
            
            # Format phone to international format
            # phone = order._format_phone_for_whatsapp(raw_phone, phone_partner)
            
            # if not phone:
            #     _logger.warning("⚠️ [WEBSITE-ORDER] Phone formatting failed for order %s", order.name)
            #     try:
            #         order.write({"whatsapp_last_error_website": "Invalid phone number"})
            #         self.env.cr.commit()
            #     except:
            #         pass
            #     continue
            
            # _logger.info("📞 [WEBSITE-ORDER] Formatted phone for WhatsApp: %s", phone)
            
            # Check Cloudinary configuration
            if not all([cloud_name, api_key, api_secret]):
                _logger.error("❌ [WEBSITE-ORDER] Cloudinary not configured!")
                try:
                    order.write({"whatsapp_last_error_website": "Cloudinary not configured"})
                    self.env.cr.commit()
                except:
                    pass
                continue
            
            # Generate PDF
            pdf_result = order._generate_website_order_pdf()
            
            if not pdf_result[0]:
                _logger.error("❌ [WEBSITE-ORDER] PDF generation failed for %s", order.name)
                try:
                    order.write({"whatsapp_last_error_website": "PDF generation failed"})
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
                _logger.error("❌ [WEBSITE-ORDER] Cloudinary upload failed for %s", order.name)
                try:
                    order.write({"whatsapp_last_error_website": "Cloudinary upload failed"})
                    self.env.cr.commit()
                except:
                    pass
                continue
            
            # Save URL and mark as sent
            try:
                order.write({
                    "cloudinary_pdf_url_website": pdf_url,
                    "whatsapp_sent_website": True,
                    "whatsapp_last_error_website": False
                })
                self.env.cr.commit()
            except Exception as e:
                _logger.error("❌ [WEBSITE-ORDER] Could not mark as sent: %s", e)
            
            # Prepare WhatsApp message
            # Use shipping address name if available, otherwise use partner name
            customer_name = order.partner_shipping_id.name if order.partner_shipping_id else order.partner_id.name
            customer_name = customer_name or "Customer"
            body_params = [customer_name]
            
            _logger.info("📝 [WEBSITE-ORDER] Customer name for WhatsApp: %s", customer_name)
            
            token = whatsapp_auth.replace("Bearer ", "").strip() if whatsapp_auth else ""
            
            # Send WhatsApp message
            order._send_whatsapp_template(
                whatsapp_url, template_name, language_code, pdf_url,
                body_params, raw_phone, token
            )

    @api.model
    def _cron_send_pending_website_order_whatsapp(self, limit=20):
        """Send pending website order WhatsApp notifications outside checkout requests."""
        Param = self.env["ir.config_parameter"].sudo()
        sales_enabled = Param.get_param("pos_webhook_notify.enable_sales", "True") == "True"

        if not sales_enabled:
            _logger.info("[WEBSITE-ORDER-CRON] Sales module is DISABLED. Skipping.")
            return

        orders = self.sudo().search([
            ("website_id", "!=", False),
            ("state", "in", ("sale", "done")),
            ("whatsapp_sent_website", "=", False),
        ], order="write_date asc, id asc", limit=limit)

        if not orders:
            _logger.info("[WEBSITE-ORDER-CRON] No pending website orders.")
            return

        _logger.info("[WEBSITE-ORDER-CRON] Processing %d pending website order(s)", len(orders))
        orders._send_website_order_whatsapp()

    def _queue_website_order_whatsapp(self):
        """Leave website orders for the cron worker to avoid breaking checkout."""
        website_orders = self.filtered(
            lambda order: order.website_id
            and order.state in ("sale", "done")
            and not order.whatsapp_sent_website
        )
        if website_orders:
            _logger.info(
                "[WEBSITE-ORDER] Queued %d order(s) for cron WhatsApp processing: %s",
                len(website_orders),
                ", ".join(website_orders.mapped("name")),
            )

    def action_confirm(self):
        """Override action_confirm to trigger WhatsApp sending when website order is confirmed"""
        res = super(SaleOrder, self).action_confirm()
        
        # Check if Sales module is enabled
        Param = self.env["ir.config_parameter"].sudo()
        sales_enabled = Param.get_param("pos_webhook_notify.enable_sales", "True") == "True"
        
        if not sales_enabled:
            _logger.info("🔴 [WEBSITE-ORDER] Sales module is DISABLED. Skipping WhatsApp.")
            return res
        
        # Filter for website orders that should trigger WhatsApp
        website_orders_to_notify = self.filtered(
            lambda order: order.website_id and 
                         order.state in ('sale', 'done') and 
                         not order.whatsapp_sent_website
        )
        
        if website_orders_to_notify:
            _logger.info("📨 [WEBSITE-ORDER] Queueing WhatsApp for %d website order(s)",
                        len(website_orders_to_notify))
            website_orders_to_notify._queue_website_order_whatsapp()
        
        return res

    def write(self, vals):
        """Override write to catch state changes for website orders"""
        res = super(SaleOrder, self).write(vals)
        
        # Check if Sales module is enabled
        Param = self.env["ir.config_parameter"].sudo()
        sales_enabled = Param.get_param("pos_webhook_notify.enable_sales", "True") == "True"
        
        if not sales_enabled:
            return res
        
        # If state changed to 'sale' or 'done', trigger WhatsApp for website orders
        if 'state' in vals and vals['state'] in ('sale', 'done'):
            website_orders_to_notify = self.filtered(
                lambda order: order.website_id and 
                             order.state in ('sale', 'done') and 
                             not order.whatsapp_sent_website
            )
            
            if website_orders_to_notify:
                _logger.info("📨 [WEBSITE-ORDER] State change detected, queueing WhatsApp for %d order(s)",
                            len(website_orders_to_notify))
                website_orders_to_notify._queue_website_order_whatsapp()
        
        return res
