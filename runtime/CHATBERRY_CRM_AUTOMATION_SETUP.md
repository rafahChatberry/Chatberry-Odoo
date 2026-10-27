# Chatberry Odoo Module Setup Guide

## Overview

This guide explains how to install and configure the Chatberry Odoo module locally, then activate CRM WhatsApp automation.

The module supports:

- POS receipt WhatsApp notifications.
- Sales invoice WhatsApp notifications.
- CRM stage-based WhatsApp template automation.
- WhatsApp template variable mapping.
- Stage From -> Stage To automation rules.
- Sending immediately when a CRM lead/opportunity changes stage.
- Sending when a Lead is converted to an Opportunity in its current target stage.
- No WhatsApp message is sent when a Lead is first created.
- WhatsApp logs, retry, cancel, and force resend actions.

The module is built for Odoo 18.

## 1. Requirements

Install these before starting:

- Docker
- Docker Compose
- A WhatsApp API endpoint and token
- A Cloudinary account only if you want to use header media attachments

The local project already includes:

- `Dockerfile`
- `docker-compose.yml`
- `custom_addons/pos_webhook_notify`

## 2. Start Odoo Locally

Open PowerShell in the project directory:

```powershell
cd C:\Users\DELL\Downloads\Odoo_Custom_Module_v1.2
```

Start the services:

```powershell
docker compose up -d --build
```

Open Odoo:

```text
http://localhost:8069
```

If the database already exists, log in with the admin user.

If the admin password is unknown, reset it:

```powershell
docker compose exec -T odoo odoo shell -d odoo --db_host=db --db_user=odoo --db_password=odoo
```

Then run inside the Odoo shell:

```python
env.ref('base.user_admin').write({'password': 'admin'})
env.cr.commit()
exit()
```

Login with:

```text
Login: admin
Password: admin
```

## 3. Install or Upgrade the Module

Run this command after copying the module or after any code update:

```powershell
docker compose exec -T odoo odoo -d odoo -u pos_webhook_notify --stop-after-init --no-http --db_host=db --db_user=odoo --db_password=odoo
docker compose restart odoo
```

Verify Odoo is running:

```powershell
docker compose ps
```

Open:

```text
http://localhost:8069/web/login
```

## 4. Configure WhatsApp API

In Odoo, go to:

```text
Settings -> POS Webhook
```

In the WhatsApp settings section, fill:

```text
WhatsApp API URL
API Authorization Token
Template Name
Language Code
```

Example:

```text
WhatsApp API URL: https://dashboard.chatberry.net/api/send/template
API Authorization Token: Bearer YOUR_TOKEN
```

Save the settings.

These API settings are shared by POS, Sales, Website Sales, and CRM automation.

## 5. Enable CRM WhatsApp Automation

In Odoo, go to:

```text
Settings -> POS Webhook
```

Enable:

```text
CRM Stage Automation
```

Configure queue settings:

```text
Queue Batch Size: 20
Max Retries: 3
Retry Delay (Minutes): 15
```

Save the settings.

CRM automation sends immediately after a matching stage transition or Lead-to-Opportunity conversion. Creating a Lead by itself never sends a message. The queue and cron remain available for retries.

## 6. Create a WhatsApp Template

Go to:

```text
CRM -> Configuration -> Chatberry WhatsApp -> WhatsApp Templates
```

Click `New`.

Fill:

```text
Name: Internal Odoo name
WhatsApp Template Name: The approved template name from WhatsApp
Language Code: en
Active: Enabled
Header Media Type: None, Image, Video, or Document
Header Media Source: None, URL, Odoo Attachment, or Lead Field
```

Example:

```text
Name: copy_2 - Qualified Invoice
WhatsApp Template Name: copy_2
Language Code: en
Header Media Type: None
Header Media Source: None
```

## 7. Configure Variable Mapping

Open the template and go to the `Variables` tab.

Each WhatsApp variable must have a mapping row.

Example WhatsApp template:

```text
Hello {{1}},

An invoice has been generated for your order.

Amount Due: {{2}} KD.
Payment Link is : {{3}} .
Note: This link is designated for completing your transaction. Please do not share it with others.
```

Example Odoo mapping:

```text
{{1}} -> contact_name
{{2}} -> stage_id.name
{{3}} -> website
```

Create these rows:

```text
Position: 1
Name: Customer Name
Component: Body
Value Type: Lead Field Path
Field Path: contact_name
Fallback: Customer
Required: Enabled
```

```text
Position: 2
Name: Target Stage Name
Component: Body
Value Type: Lead Field Path
Field Path: stage_id.name
Fallback: Qualified
Required: Enabled
```

```text
Position: 3
Name: Payment Link
Component: Body
Value Type: Lead Field Path
Field Path: website
Fallback: Payment link not available
Required: Enabled
```

Common CRM lead field paths:

```text
name
contact_name
partner_id.name
stage_id.name
user_id.name
team_id.name
mobile
phone
email_from
website
expected_revenue
```

Do not use Python expressions. Only safe field paths are supported.

## 8. Header Media Support

Header media is optional.

Supported types:

```text
None
Image
Video
Document
```

Supported sources:

```text
None
URL
Odoo Attachment
Lead Field
```

Examples:

Use a public URL:

```text
Header Media Type: Document
Header Media Source: URL
Header Media URL: https://example.com/file.pdf
```

Use a field from the CRM lead:

```text
Header Media Type: Document
Header Media Source: Lead Field
Header Field Path: website
```

Use an Odoo attachment:

```text
Header Media Type: Document
Header Media Source: Odoo Attachment
Header Attachment: Select file
```

For Odoo attachments, configure Cloudinary in:

```text
Settings -> POS Webhook -> Cloudinary Configuration
```

## 9. Button Variables Support

If the WhatsApp template contains button variables, configure them in the `Buttons` tab of the template.

Create a button:

```text
Button Index: 0
Name: Open Payment Link
Button Type: URL
```

Then add variables for that button:

```text
Component: Button
Position: 1
Value Type: Lead Field Path
Field Path: website
Fallback: https://example.com
Required: Enabled
```

## 10. Create Stage Automation

Go to:

```text
CRM -> Configuration -> Chatberry WhatsApp -> Stage Automations
```

Click `New`.

Fill:

```text
Active: Enabled
Stage From: Optional source stage
Stage To: Target stage
Send On Creation: Disabled
Send On Lead Conversion: Enabled or Disabled
Template: Select WhatsApp template
Recipient Strategy: First Available
Duplicate Policy: Once Per Lead and Stage
```

`Send On Creation` is a legacy setting and must remain disabled for this workflow. A new Lead does not trigger a message. Use `Send On Lead Conversion` to send when the user clicks **Convert to Opportunity**. For conversion rules, leave `Stage From` empty because the conversion event has no source-stage transition.

### Example 1: Send when moving from New to Qualified

```text
Stage From: New
Stage To: Qualified
Send On Creation: Disabled
Send On Lead Conversion: Disabled
Template: copy_2 - Qualified Invoice
Recipient Strategy: First Available
Duplicate Policy: Once Per Lead and Stage
```

This sends only when a lead moves from `New` to `Qualified`.

### Example 2: Send when moving from any stage to Qualified

```text
Stage From: Empty
Stage To: Qualified
Send On Creation: Disabled
Send On Lead Conversion: Disabled
Template: copy_2 - Qualified Invoice
Recipient Strategy: First Available
Duplicate Policy: Once Per Lead and Stage
```

This sends when an opportunity moves from any stage to `Qualified`. It does not send on Lead creation or conversion.

### Example 3: Send when a new Lead is converted in the first stage (`New`)

Create an automation:

```text
Stage From: Empty
Stage To: New
Send On Creation: Disabled
Send On Lead Conversion: Enabled
Template: Select template
Recipient Strategy: First Available
Duplicate Policy: Once Per Lead and Stage
```

Expected behavior:

1. Creating a Lead in `New` does not send a message.
2. Clicking **Convert to Opportunity** while the record is in `New` triggers the template linked to this rule.
3. The conversion rule must be active, its template must be active, and CRM Stage Automation must be enabled in Settings.
4. The conversion is detected even if Odoo keeps the record in the same stage during conversion.

For the specific setup where only conversion should send, do not enable `Send On Creation` and leave `Stage From` empty.

## 11. Recipient Phone Rules

The recommended recipient strategy is:

```text
First Available
```

It checks phone fields in this order:

```text
Lead Mobile
Lead Phone
Partner Mobile
Partner Phone
```

If no phone number is found, the log will fail with:

```text
No phone number found for selected recipient strategy.
```

Fix it by adding a phone number to the CRM lead:

```text
CRM -> Pipeline -> Open Lead -> Mobile or Phone
```

Use international format, for example:

```text
+965XXXXXXXX
```

## 12. Deploy and Test the Conversion Workflow

The conversion trigger requires the updated Chatberry code and an Odoo module upgrade. Do not try to enable `Send On Lead Conversion` before deploying and upgrading the module; the field will not exist in the older database schema.

Before upgrading a production instance:

1. Back up the Odoo database and filestore.
2. Deploy the updated `pos_webhook_notify` module files to the production addons path.
3. Restart Odoo and upgrade the module:

```powershell
docker compose exec -T odoo odoo -d YOUR_DATABASE -u pos_webhook_notify --stop-after-init --no-http --db_host=db --db_user=odoo --db_password=odoo
docker compose restart odoo
```

Replace `YOUR_DATABASE` and the database connection arguments with the values used by your deployment. For managed hosting, use its supported Apps/module upgrade procedure instead of this Docker command.

Configure the rule under:

```text
CRM -> Configuration -> Chatberry WhatsApp -> Stage Automations
```

For the `New` stage rule, set:

```text
Stage From: Empty
Stage To: New
Send On Creation: Disabled
Send On Lead Conversion: Enabled
Template: Your approved template for New
Active: Enabled
```

Then test:

1. Create a Lead in `New` with a valid phone number. Confirm no WhatsApp message is sent at creation.
2. Open the Lead and click **Convert to Opportunity**.
3. Open **WhatsApp Logs** and confirm a log was created for the `New` automation and the expected template.
4. Confirm the status is `Sent`; if it is `Failed` or `Skipped`, inspect the log's `Error`, `Response`, and `Payload` tabs.

Open CRM to create the test Lead:

```text
CRM -> Sales -> My Pipeline
```

Check logs:

```text
CRM -> Configuration -> Chatberry WhatsApp -> WhatsApp Logs
```

Expected statuses:

```text
Sent
Failed
Skipped
Queued
```

The conversion-triggered message is attempted immediately after conversion. Ordinary stage-change automations still run when an opportunity moves to a different target stage.

## 13. WhatsApp Logs

Go to:

```text
CRM -> Configuration -> Chatberry WhatsApp -> WhatsApp Logs
```

Each log shows:

```text
Lead
Automation
Template
Phone
From Stage
To Stage
Attempts
Max Attempts
Payload
Response
Error
```

Available actions:

```text
Retry
Cancel
Force Resend
```

Use `Retry` after fixing a phone number, API URL, token, or template mapping.

## 14. Duplicate Sending Protection

Default duplicate policy:

```text
Once Per Lead and Stage
```

This prevents sending the same automation repeatedly for the same lead and target stage.

If a duplicate happens, the system creates or records a skipped status:

```text
Skipped
```

To send again manually, open the related log and use:

```text
Force Resend
```

## 15. Troubleshooting

### WhatsApp API URL is not configured

Go to:

```text
Settings -> POS Webhook
```

Fill:

```text
WhatsApp API URL
API Authorization Token
```

Save and retry the failed log.

### No phone number found for selected recipient strategy

The CRM lead does not have a phone number.

Add a value to:

```text
Mobile
```

or:

```text
Phone
```

Then retry.

### The provided data is invalid

Usually caused by:

- Invalid phone number format.
- WhatsApp template name does not match the approved template.
- Wrong language code.
- Wrong number of variables.
- Button/header configuration does not match the approved template.

Open the failed log and check:

```text
Payload
Response
Error
```

### Template was sent on Lead creation

The updated workflow does not send on Lead creation. Check that the production server has the updated module code and that the module was upgraded. Also disable `Send On Creation` on the rule. If the old module version is still running, it may retain the previous creation-trigger behavior.

### Template does not send on Lead conversion

Check the automation:

```text
Send On Creation: Disabled
Send On Lead Conversion: Enabled
Stage From: Empty
Stage To: The Lead's current stage at conversion (for example, New)
Active: Enabled
```

Also confirm the code has been deployed and `pos_webhook_notify` upgraded after deployment. Conversion is detected on the Lead-to-Opportunity type change, even if the stage remains `New`.

### Template does not send on stage move

Check:

```text
Stage From
Stage To
Active
Template Active
CRM Stage Automation enabled in Settings
```

If `Stage From` is set, the lead must move from exactly that stage.

If `Stage From` is empty, any previous stage is accepted.

## 16. Useful Docker Commands

View logs:

```powershell
docker compose logs -f odoo
```

Filter Chatberry logs:

```powershell
docker compose logs -f odoo | Select-String "CHATBERRY"
```

Upgrade module:

```powershell
docker compose exec -T odoo odoo -d odoo -u pos_webhook_notify --stop-after-init --no-http --db_host=db --db_user=odoo --db_password=odoo
docker compose restart odoo
```

Open Odoo shell:

```powershell
docker compose exec -T odoo odoo shell -d odoo --db_host=db --db_user=odoo --db_password=odoo
```

Manually process retry queue:

```python
env['chatberry.whatsapp.message.log'].sudo()._cron_process_queue()
env.cr.commit()
```

## 17. Recommended Client Workflow

1. Configure WhatsApp API.
2. Create WhatsApp template records in Odoo.
3. Add variable mapping for each template.
4. Create CRM stage automation rules.
5. Test with one CRM lead that has a valid phone number.
6. Check WhatsApp Logs.
7. Adjust mapping or template settings if needed.
8. Enable more automations stage by stage.

