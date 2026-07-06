{
    "name": "Chatberry",
    "version": "1.0.0",
    "summary": "Sends POS receipt PDFs and Sales invoice PDFs to customers via WhatsApp when orders are paid.",
    "author": "ObsidianX",
    "category": "Point of Sale",
    "license": "LGPL-3",
    "depends": ["base", "point_of_sale", "account", "sale", "website_sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/pos_receipt_template.xml", 
    ],
    "images": ["static/description/icon.png"], 
    "installable": True,
    "application": False,
    "auto_install": False,
}