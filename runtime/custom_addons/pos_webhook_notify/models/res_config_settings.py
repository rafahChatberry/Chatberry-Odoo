from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ========================================
    # ENABLE/DISABLE TOGGLES (WITH PROPER HANDLING)
    # ========================================
    pos_webhook_enable_pos = fields.Boolean(
        string="Enable POS Receipt Notifications",
        help="Enable/disable WhatsApp notifications for POS orders"
    )
    pos_webhook_enable_sales = fields.Boolean(
        string="Enable Sales Invoice Notifications",
        help="Enable/disable WhatsApp notifications for Sales invoices"
    )
    pos_webhook_enable_crm = fields.Boolean(
        string="Enable CRM WhatsApp Automation",
        help="Enable/disable WhatsApp notifications when CRM stages change"
    )

    # ========================================
    # OPTIONAL JSON WEBHOOK
    # ========================================
    pos_webhook_url = fields.Char(
        string="Webhook URL (Optional)",
        help="Optional: Send order data as JSON to this endpoint",
        config_parameter="pos_webhook_notify.url"
    )
    pos_webhook_auth = fields.Char(
        string="Webhook Authorization (Optional)",
        help="e.g. 'Bearer abc123' or any header value",
        config_parameter="pos_webhook_notify.auth"
    )
    
    # ========================================
    # WHATSAPP TEMPLATE API
    # ========================================
    pos_webhook_whatsapp_url = fields.Char(
        string="WhatsApp Template API URL",
        help="URL to send template messages via WhatsApp API",
        config_parameter="pos_webhook_notify.whatsapp_url"
    )
    pos_webhook_whatsapp_auth = fields.Char(
        string="WhatsApp API Token",
        help="Authorization token for WhatsApp API",
        config_parameter="pos_webhook_notify.whatsapp_auth"
    )
    
    # ========================================
    # WHATSAPP TEMPLATE CONFIGURATION
    # ========================================
    pos_webhook_template_name = fields.Char(
        string="Template Name",
        help="The name of your WhatsApp template",
        default="payment_confirmation_2",
        config_parameter="pos_webhook_notify.template_name"
    )
    pos_webhook_language_code = fields.Char(
        string="Template Language Code",
        help="Language code for the template",
        default="en",
        config_parameter="pos_webhook_notify.language_code"
    )
    
    # ========================================
    # CLOUDINARY CONFIGURATION
    # ========================================
    pos_webhook_cloudinary_cloud_name = fields.Char(
        string="Cloudinary Cloud Name",
        help="Your Cloudinary cloud name",
        config_parameter="pos_webhook_notify.cloudinary_cloud_name"
    )
    pos_webhook_cloudinary_api_key = fields.Char(
        string="Cloudinary API Key",
        help="Your Cloudinary API key",
        config_parameter="pos_webhook_notify.cloudinary_api_key"
    )
    pos_webhook_cloudinary_api_secret = fields.Char(
        string="Cloudinary API Secret",
        help="Your Cloudinary API secret",
        config_parameter="pos_webhook_notify.cloudinary_api_secret"
    )

    # ========================================
    # CRM QUEUE CONFIGURATION
    # ========================================
    pos_webhook_crm_queue_batch_size = fields.Integer(
        string="CRM Queue Batch Size",
        default=20,
        config_parameter="pos_webhook_notify.crm_queue_batch_size"
    )
    pos_webhook_crm_max_retries = fields.Integer(
        string="CRM Max Retries",
        default=3,
        config_parameter="pos_webhook_notify.crm_max_retries"
    )
    pos_webhook_crm_retry_delay_minutes = fields.Integer(
        string="CRM Retry Delay (Minutes)",
        default=15,
        config_parameter="pos_webhook_notify.crm_retry_delay_minutes"
    )

    # ========================================
    # GETTER METHODS FOR BOOLEAN FIELDS
    # ========================================
    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        
        # Get boolean values properly
        pos_enabled = IrConfigParameter.get_param('pos_webhook_notify.enable_pos', 'True')
        sales_enabled = IrConfigParameter.get_param('pos_webhook_notify.enable_sales', 'True')
        crm_enabled = IrConfigParameter.get_param('pos_webhook_notify.enable_crm', 'True')
        
        res.update(
            pos_webhook_enable_pos=(pos_enabled == 'True'),
            pos_webhook_enable_sales=(sales_enabled == 'True'),
            pos_webhook_enable_crm=(crm_enabled == 'True'),
        )
        return res

    # ========================================
    # SETTER METHODS FOR BOOLEAN FIELDS
    # ========================================
    def set_values(self):
        super(ResConfigSettings, self).set_values()
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        
        # Set boolean values as strings
        IrConfigParameter.set_param('pos_webhook_notify.enable_pos', 
                                     'True' if self.pos_webhook_enable_pos else 'False')
        IrConfigParameter.set_param('pos_webhook_notify.enable_sales', 
                                     'True' if self.pos_webhook_enable_sales else 'False')
        IrConfigParameter.set_param('pos_webhook_notify.enable_crm',
                                     'True' if self.pos_webhook_enable_crm else 'False')
