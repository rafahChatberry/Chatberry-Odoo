Chatberry - Technical Documentation
# Chatberry
## Odoo WhatsApp Invoice Notification Module
## Complete Technical Implementation Documentation
Module Name Chatberry
Version 1.0.0
Odoo Version 18.0
Author ObsidianX
License LGPL - 3
Last Updated November 2024
Page 1 of 17

---

Chatberry - Technical Documentation
## Table of Contents
Table of Contents ................................ ................................ ................................ .................. 2
Executive Summary ................................ ................................ ................................ .............. 4
Key Features ................................ ................................ ................................ ..................... 4
Business Value ................................ ................................ ................................ .................. 4
Technical Stack & Architecture ................................ ................................ ............................. 4
Technology Components ................................ ................................ ................................ ... 4
System Architecture ................................ ................................ ................................ .......... 4
Module Structure & Organization ................................ ................................ .......................... 5
Directory Layout ................................ ................................ ................................ ................ 5
Module Dependencies ................................ ................................ ................................ ....... 5
Configuration System ................................ ................................ ................................ ............ 7
Configuration Parameters ................................ ................................ ................................ .. 7
Core Models Implementation ................................ ................................ ................................ 7
1. POS Order Model (pos_ord er.py) ................................ ................................ .................. 7
Additional Fields ................................ ................................ ................................ ............. 8
Key Methods ................................ ................................ ................................ .................. 8
2. Account Move Model (account_move.py) ................................ ................................ ...... 8
Additional Fields ................................ ................................ ................................ ............. 8
Key Methods ................................ ................................ ................................ .................. 9
3. Sale Order Model (sale_order.py) ................................ ................................ .................. 9
Additional Fields ................................ ................................ ................................ ............. 9
Key Methods ................................ ................................ ................................ .................. 9
PDF Generation System ................................ ................................ ................................ ..... 10
Custom POS Receipt Template ................................ ................................ ....................... 10
Template Components ................................ ................................ ................................ . 10
Template Fallback Strategy ................................ ................................ ............................. 10
PDF Validation ................................ ................................ ................................ ................ 10
Cloudinary Integration ................................ ................................ ................................ ......... 11
Upload Process ................................ ................................ ................................ ............... 11
Benefits of Cloudinary ................................ ................................ ................................ ..... 11
WhatsApp Integration ................................ ................................ ................................ .......... 11
WhatsApp Template Structure ................................ ................................ ......................... 12
API Request Format ................................ ................................ ................................ ........ 12
Request Payload Structure ................................ ................................ .......................... 12
Asynchronous Processing ................................ ................................ ............................... 12
Process Workflows ................................ ................................ ................................ ............. 12
POS Order Workflow ................................ ................................ ................................ ....... 13
Page 2 of 17

---

Chatberry - Technical Documentation
Sales Invoice Workflow ................................ ................................ ................................ ... 13
Website Order Workflow ................................ ................................ ................................ .. 13
Error Handling & Logging ................................ ................................ ................................ .... 14
Logging System ................................ ................................ ................................ ............... 14
Error Field Storage ................................ ................................ ................................ .......... 14
Security & Access Control ................................ ................................ ................................ ... 14
Model Access Rights ................................ ................................ ................................ ....... 14
Configuration Security ................................ ................................ ................................ ..... 15
Installation & Deployment ................................ ................................ ................................ ... 15
Prerequisites ................................ ................................ ................................ ................... 15
Docker Configuration ................................ ................................ ................................ ....... 15
Installation Steps ................................ ................................ ................................ ............. 15
Post - Installation Configuration ................................ ................................ ......................... 15
Troubleshooting Guide ................................ ................................ ................................ ........ 16
Common Issues and Solutions ................................ ................................ ........................ 16
Debugging Steps ................................ ................................ ................................ ............. 16
Performance Considerations ................................ ................................ ............................... 16
Current Performance Charact eristics ................................ ................................ ............... 16
Optimization Techniques ................................ ................................ ................................ . 17
Conclusion ................................ ................................ ................................ .......................... 17
Key Achievements ................................ ................................ ................................ ........... 17
Future Enhancements ................................ ........................ Error! Bookmark not defined.
Support & Maintenance ................................ ...................... Error! Bookmark not defined.
Page 3 of 17

---

Chatberry - Technical Documentation
## Executive Summary
Chatberry is a custom Odoo 18 module that automatically sends invoice and receipt PDFs to
customers via WhatsApp after payment completion. The module provides seamless
integration across multiple sales channels inc luding Point of Sale (POS), Sales Orders, and
e - commerce Website Orders.
### Key Features
- Automatic WhatsApp notifications with PDF attachments
- Cloudinary integration for secure PDF hosting
- Custom POS receipt template matching invoice format
- Independent enable/disable controls for POS and Sales
- Asynchronous processing using threading for non - blocking operations
- Comprehensive error tracking and logging system
- Optional JSON webhook support for custom integrations
- Template - based WhatsApp messagin g for consistent branding
### Business Value
This module addresses critical business needs by providing immediate, automated customer
communication for completed transactions. It eliminates manual processes, reduces
response time, and enhances customer experi ence through instant delivery of professional
PDF receipts and invoices directly to customers' mobile devices via WhatsApp.
## Technical Stack & Architecture
### Technology Components
Component Technology Purpose
ERP System Odoo 18.0 Core business logic
Programming Python 3.10+ Module implementation
Container Docker & Compose Deployment platform
PDF Hosting Cloudinary Public URL hosting
Messaging WhatsApp Business API Customer notifications
Database PostgreSQL 15 Data persistence
Libraries requests, cloudinary HTTP & cloud operations
### System Architecture
The module follows a layered architecture with clear separation of concerns:
Page 4 of 17

---

Chatberry - Technical Documentation
1. Presentation Layer: XML views for configuration management in Odoo's settings
interface
2. Business Logic Layer: Python models extending POS Order, Account Move, and
Sale Order with notification logic
3. Integration Layer: HTTP APIs for Cloudinary and WhatsApp communication
4. Data Layer: PostgreSQL database with Odoo ORM for persistence
## M odule Structure & Organization
### D irectory Layout
pos_webhook_notify/
├── __init__.py # Module initialization
├── __manifest__.py # Module metadata
│
├── models/ # Business logic
│ ├── __init__.py
│ ├── res_config_settings.py # Configuration model
│ ├── pos_order.py # POS order processing
│ ├── account_move.py # Invoice processing
│ └── sale_order.py # Sales order processing
│
├── views/ # User interface
│ ├── res_config_settings_views.xml # Settings page
│ └── pos_receipt_template.xml # POS receipt template
│
├── security/ # Access control
│ └── ir.model.acces s.csv # Model access rights
│
└── static/ # Static assets
└── description/
└── icon.png # Module icon
### Module Dependencies
The module declares the following dependencies in __manifest_ _.py:
Module Purpose
base Core Odoo framework and configuration system
point_of_sale POS functionality and order models
Page 5 of 17

---

Chatberry - Technical Documentation
Module Purpose
account Invoicing and accounting move models
sale Sales order management
website_sale E - commerce integration for website orders
Page 6 of 17

---

Chatberry - Technical Documentation
## Configuration System
The module uses Odoo's ir.config_parameter system for persistent configuration storage. All
settings are managed through a dedicated configuration page accessible from Settings →
POS Webhook.
### Configuration Parameters
Parameter Key De fault Description
Module Control
enable_pos True Enable POS notifications
enable_sales True Enable Sales notifications
WhatsApp API
whatsapp_url - WhatsApp template API
URL
whatsapp_auth - WhatsApp API
authorization token
template_name payment_confirmation_2 WhatsApp template name
language_code en Template language code
Cloudinary
cloudinary_cloud_name - Cloudinary cloud name
cloudinary_api_key - Cloudinary API key
cloudinary_api_secret - Cloudinary API secret
(secure)
## Core Models Implementation
The module extends three core Odoo models to add WhatsApp notification capabilities.
Each model follows a similar pattern of PDF generation, Cloudinary upload, and
asynchronous WhatsApp messaging.
1. POS Order Model (pos_order.p y)
Inheritance: pos.order
Purpose: Handles Point of Sale receipt generation and delivery via WhatsApp when orders
are paid.
Page 7 of 17

---

Chatberry - Technical Documentation
### Additional Fields
Field Name Type Purpose
webhook_sent Boolean Tracks if JSON webhook was sent
webhook_last_error Char Stores webhook error message
whatsapp_sent Boolean Tracks if WhatsApp was sent
whatsapp_last_error Char Stores WhatsApp error message
cloudinary_pdf_url Char Public URL of uploaded PDF
### Key Methods
_generate_receipt_pdf()
Generates POS receipt PDF using custom template. Falls back to automatic invoice creation
if custom template fails.
Returns: tuple(bytes, str) - PDF content and filename
Template: pos_webhook_notify.report_pos_receipt_custom
_upload_to_cloudinary()
Uploa ds PDF to Cloudinary using HTTP API with signature authentication.
Parameters: pdf_content, filename, cloud_name, api_key, api_secret
Returns: str - Public URL or None
Endpoint: https://api.cloudinary.com/v1_1/{cloud}/raw/upload
_send_whatsapp_template()
Sends WhatsApp template message with PDF attachment. Executes asynchronously in
background thread.
Threading: Daemon thread with 0.5s delay
Returns: None (async execution)
_send_pos_webhook()
Main orchestration method that coordinates PDF generation, up load, and WhatsApp
dispatch.
2. Account Move Model (account_move.py)
I nheritance: account.move
Purpose: Handles sales invoice PDF generation and delivery via WhatsApp when invoices
are posted.
### Additional Fields
Page 8 of 17

---

Chatberry - Technical Documentation
Field Name Type Purpose
whatsapp_sent Boolean Indicates if invoice sent via WhatsApp
whatsapp_last_error Char Last error message from sending attempt
cloudinary_pdf_url Char Public URL of invoice PDF on Cloudinary
### Key Methods
_generate_sales_invoice_pdf()
Generates invoice PDF using standard Odoo invoice templates with fallback support.
Templates tried in order:
1. account.report_invoice_with_payments
2. account.report_invoice
3. account.account_invoices
_send_sales_invoice_whatsapp()
Main orchestration method that handles the complete workflow for invoice notifications.
Method Override: action_post()
Intercepts invoice posting to trigger WhatsApp notifications for customer invoices
(out_invoice).
3. Sale Order Model (sale_order.py)
Inheritance: sale.order
Purpose: Handles website order confirmations and delivery via WhatsApp for e - commerce
orders.
### Additional Fields
Field Name Type Purpose
whatsapp_sent_website Boolean Website order confirmation sent
whatsapp_last_error_website Char Website order error message
cloudinary_pdf_url_website Char Public URL of order PDF
### Key Methods
_generate_website_order_pdf()
Generates order confirmation PDF using sale order templates.
_send_website_order_whatsapp()
Handles website order notification workflow with shipping address priority.
Page 9 of 17

---

Chatberry - Technical Documentation
Method Override: action_confirm() & write()
Intercepts order confirmation to trigger WhatsApp for website orders.
## PDF Generation System
The module implements a sophisticated PDF generation system with custom templates and
fallback mechanisms to ensure reliable receipt and invoice delivery.
### Custom POS Receipt Template
The module includes a custom QWeb template for POS receipts that matches professional
invoice formatting:
### Template Components
5. Header Section: Customer name (right - aligned), Invoice title with order number
6. Invoice Details Grid: 4 - column layout with Invoice Date, Due Date, Source, and
Reference
7. Product Table: Description, Quant ity, Unit Price, Taxes, and Amount columns
8. Payment Communication: Order reference for payment tracking
9. Summary Section: Untaxed amount, Tax calculation, Total, Payment method,
Amount due
### Template Fallback Strategy
To ensure reliability, the system impleme nts a multi - level fallback strategy:
For POS Orders:
10. Try custom POS receipt template
11. If fails, automatically create invoice
12. Try standard invoice templates (3 templates)
For Sales Invoices:
13. account.report_invoice_with_payments
14. account.report_invoice
15. accou nt.account_invoices
For Website Orders:
16. sale.action_report_saleorder
17. sale.report_saleorder
18. sale_management.report_saleorder_pro_forma
### PDF Validation
Each generated PDF undergoes strict validation:
- Type check: Must be bytes
- Size check: Must not be empty
Page 10 of 17

---

Chatberry - Technical Documentation
- Format check: Must start with '%PDF' signature
## C loudinary Integration
Cloudinary is used for PDF hosting because WhatsApp requires publicly accessible URLs
for document attachments. The module implements direct HTTP upload without using the
Cloudinary SD K.
### Upload Process
Step 1: Endpoint Construction
https://api.cloudinary.com/v1_1/{cloud_name}/raw/upload
Step 2: Folder Organization
invoices/{YYYY}/{MM}
Example: invoices/2024/11
Step 3: Signature Generation
Cloudinary requires SHA1 signature for securi ty. The signature is generated using sorted
parameters:
SHA1(folder=value&invalidate=value&overwrite=value&public_id=value&
timestamp=value<api_secret>)
Step 4: HTTP POST Request
Multipart form - data upload with signature authentication
Step 5: URL Storage
The returned secure_url is stored in the order/invoice record for future reference
### Benefits of Cloudinary
Feature Benefit
Public URLs Required for WhatsApp document sharing
CDN Distribution Fast global access with low latency
Reliability 99.99% uptime SLA with redundant storage
Free Tier 25 GB storage and 25 GB bandwidth per month
Security Signature - based authentication and HTTPS delivery
## WhatsApp Integration
Page 11 of 17

---

Chatberry - Technical Documentation
The module uses WhatsApp's Template Message API for sending stru ctured, approved
messages with document attachments.
### WhatsApp Template Structure
Required Components:
19. Header: Document attachment (PDF link)
20. Body: Message text with placeholders
21. Language: Template language code
### API Request Format
POST /api/send/template
Content - Type: application/json
Authorization: Bearer {token}
### Request Payload Structure
{
phone: Customer phone number
template: {
name: Template name
language: { code: Language code }
components: [
{ type: header, parameters: [docum ent link] }
{ type: body, parameters: [customer name] }
]
}
}
### Asynchronous Processing
WhatsApp messages are sent asynchronously using Python threading to prevent blocking
the main Odoo process:
- Daemon thread: Automatically terminated when main process exits
- 0.5 second delay: Ensures order data is committed to database
- Non - blocking: User interface remains responsive during sending
- Error isolation: Failures don't affect transaction completion
## P rocess Workflows
Page 12 of 17

---

Chatberry - Technical Documentation
The module implements three parallel workflows for different transaction types, all following
a similar pattern but with specific variations.
### POS Order Workflow
Trigger Points:
- sync_from_ui() - When order syncs from POS terminal
- write() - When order state changes to 'paid' or 'invoiced'
Process Steps:
22. Check if POS module is enabled in settings
23. Verify order not already sent (whatsapp_sent = False)
24. Validate customer has phone number
25. Confirm Cloudinary credentials are configured
26. Generate P DF using custom template (with invoice fallback)
27. Upload PDF to Cloudinary and get public URL
28. Update order record with PDF URL and mark as sent
29. Send WhatsApp template message asynchronously
### Sales Invoice Workflow
Trigger Point:
- action_post() - When invoice is confirmed/posted
Process Steps:
30. Check if Sales module is enabled
31. Filter for customer invoices only (move_type = 'out_invoice')
32. Verify invoice is in 'posted' state
33. Validate customer has phone number
34. Generate PDF using standard invoice templates
35. Upload to Cloudinary
36. Mark invoice as sent
37. Send WhatsApp notification
### Website Order Workflow
Trigger Points:
- action_confirm() - When order is confirmed
- write() - When order state changes to 'sale' or 'done'
Process Steps:
38. Check if Sales module is enabled
39. Verify order is from website (website_id exists)
40. Check phone from shipping address first, then billing address
41. Generate order confirmation PDF
42. Upload to Cloudinary
43. Mark order as sent
Page 13 of 17

---

Chatberry - Technical Documentation
44. Send WhatsApp with shipping contact name
## E rror Handling & Logging
The module implements comprehensive error handling with structured logging using emoji
prefixes for easy visual scanning of log files.
### Logging System
Level Emoji Usage
INFO 🔍 🔍 🔍 Process steps and normal operations
WARNING 🔍 Non - critical issues that don't stop processing
ERROR ❌ 🔍 Failures that prevent notification sending
EXCEPTION ❌ Exceptions with full stack trace
### Error Field Storage
Errors are stored in database fields for tracking and debugging:
- whatsapp_last_error - Stores error message
- whatsapp_sent - Remains False on failure
- cloudinary_pdf_url - Empty if upload fails
Common Error Messages:
- No phone number
- Cloudinary not configured
- PDF generation failed
- Cloudinary upload failed
## S ecurity & Acc ess Control
### Model Access Rights
Access control is defined in ir.model.access.csv:
Model Group Permissions Delete
pos.order Internal Users Read, Write, No
Create
account.move Internal Users Read, Write, No
Create
Page 14 of 17

---

Chatberry - Technical Documentation
Model Group Permissions Delete
sale.order Internal Users Read, Write, No
Create
### Configuration Security
Sensitive configuration fields are marked as password fields:
- WhatsApp API token - Password field
- Cloudinary API secret - Password field
- Optional webhook auth - Password field
All configuration parameters are accessed via sudo() for proper security context.
## Installation & Deployment
### Prerequisites
- Docker and Docker Compose installed
- Cloudinary account (free tier available)
- WhatsApp Business API access
- Basic understanding of Odoo module installation
### Docker Configuration
Dockerfile:
FROM odoo:18.0
USER root
RUN pip3 install -- no - cache - dir -- break - system - packages \
requests cloudinary
USER odoo
### Installation Steps
45. Build Docker image: docker - compose bu ild
46. Start services: docker - compose up - d
47. Access Odoo: http://localhost:8069
48. Install module: Apps → Remove 'Apps' filter → Search 'Chatberry' → Install
49. Configure: Settings → POS Webhook → Enter credentials
### Post - Installation Configuration
Navigate to Settings → POS Webhook and configure:
Page 15 of 17

---

Chatberry - Technical Documentation
50. Module Controls: Enable POS and/or Sales notifications
51. WhatsApp Settings: API URL, authorization token, template name
52. Cloudinary: Cloud name, API key, API secret
53. Optional: JSON webhook URL for custom integ rations
## T roubleshooting Guide
### Common Issues and Solutions
Issue Cause Solution
WhatsApp not sending Module disabled or Check enable toggles and
incomplete config credentials
PDF generation fails Template missing or order Check logs and verify
data incomplete order has lines
Cloudinary upload fails Invalid credentials or Verify cloud_name,
signature api_key, api_secret
Template not found Template name incorrect Check WhatsApp Business
or not approved Manager
No phone number error Customer record missing Update partner
phone mobile/phone field
### Debugging Steps
54. Check logs: docker - compose logs - f odoo | grep WHATSAPP
55. Verify configuration: Settings → POS Webhook
56. Check error fields: View order/invoice → whatsapp_last_error
57. Test manually: Use Odoo shell to call methods directly
58. Review status: Check whatsapp_sent field value
## P erformance Considerations
### Current Performance Characteristics
Operation Duration Notes
PDF Generation 0.5 - 2 seconds Depends on order complexity
Cloudinary Upload 1 - 3 seconds Network latency dependent
WhatsApp Send 0.5 - 1 second Async, doesn't block UI
Total Process 2 - 6 seconds User can continue
immediately
Page 16 of 17

---

Chatberry - Technical Documentation
### Optimization Techniqu es
- Asynchronous Processing: WhatsApp sends don't block main thread
- PDF Caching: Reuse Cloudinary URL if already uploaded
- Template Fallback: Multiple templates ensure success
- Database Commits: Immediate commits prevent data loss
- Error Isolation: Failures don't affect transaction completion
## C onclusion
The Chatberry module provides a comprehensive solution for automated customer
notifications via WhatsApp, integrating seamlessly with Odoo's Point of Sale, Sales, and E -
commerce systems. With robust error handling, asynchronous processing, and professional
PDF generation, the module enhances customer experience while maintaining system
reliability and performance.
### Key Achievements
- Multi - channel support across POS, Invoices, and Website Orders
- Professional PDF templates with custom POS receipt format
- Reliable delivery using Cl oudinary hosting and WhatsApp Business API
- Comprehensive error handling with detailed logging
- Flexible configuration with independent channel controls
- High performance with asynchronous processing
— End of Documentation —
Chatberry v1.0.0 | Odoo 18.0 | November 2024
Page 17 of 17
