# CLI Tools for App Store Server Library

This directory contains command-line tools for interacting with the App Store Server API.

## Retention Message Tool

The `retention_message.py` tool allows you to manage retention messages that can be displayed to users to encourage app re-engagement.

### Prerequisites

1. **App Store Connect Credentials**: You need:
   - Private Key ID (`key_id`) from App Store Connect
   - Issuer ID (`issuer_id`) from App Store Connect
   - Your app's Bundle ID (`bundle_id`)
   - Private key file (`.p8` format) downloaded from App Store Connect

2. **Python Dependencies**: Make sure the app-store-server-library is installed:
   ```bash
   pip install -r ../requirements.txt
   ```

### Usage

#### Upload a Retention Message

Upload a new retention message with auto-generated ID:
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/SubscriptionKey_ABCDEFGHIJ.p8" \
  --header "Welcome back!" \
  --body "Check out our new features"
```

Upload with a specific message ID:
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --message-id "my-campaign-001" \
  --header "Limited Time Sale!" \
  --body "50% off premium features this week"
```

Upload with an image:
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --header "New Update!" \
  --body "Amazing new features await" \
  --image-id "banner-v2" \
  --image-alt-text "App update banner showing new features"
```

#### List All Messages

```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action list
```

#### Delete a Message

```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action delete \
  --message-id "my-campaign-001"
```

#### Configure Default Messages

Set a message as the default for a specific product and locale. The default message is shown when the real-time messaging flow isn't available or fails.

**Single Product and Single Locale:**
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action set-default \
  --message-id "my-campaign-001" \
  --product-id "com.example.premium" \
  --locale "en-US"
```

**Multiple Products (Bulk Operation):**
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action set-default \
  --message-id "my-campaign-001" \
  --product-id "com.example.premium" \
  --product-id "com.example.basic" \
  --product-id "com.example.pro" \
  --locale "en-US"
```

**Multiple Locales (Bulk Operation):**
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action set-default \
  --message-id "my-campaign-001" \
  --product-id "com.example.premium" \
  --locale "en-US" \
  --locale "fr-FR" \
  --locale "de-DE" \
  --locale "ja"
```

**Multiple Products and Multiple Locales:**
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action set-default \
  --message-id "my-campaign-001" \
  --product-id "com.example.premium" \
  --product-id "com.example.basic" \
  --locale "en-US" \
  --locale "fr-FR" \
  --locale "de-DE"
```

This will configure the message as the default for all 6 combinations (3 products × 2 locales).

#### Delete Default Message Configuration

Remove the default message configuration for one or more products and locales.

**Delete for multiple products (single locale):**
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action delete-default \
  --product-id "com.example.premium" \
  --product-id "com.example.basic" \
  --locale "en-US"
```

**Delete for multiple locales:**
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action delete-default \
  --product-id "com.example.premium" \
  --locale "en-US" \
  --locale "fr-FR" \
  --locale "de-DE"
```

**Delete for multiple products and multiple locales:**
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action delete-default \
  --product-id "com.example.premium" \
  --product-id "com.example.basic" \
  --locale "en-US" \
  --locale "fr-FR" \
  --locale "de-DE"
```

### CSV Import (Bulk Operations)

The tool supports bulk import operations from CSV files for both message upload and default configuration. This is useful when managing multiple localized messages or large-scale updates.

#### CSV Format Requirements

**For Message Upload (`import-csv`):**

Your CSV must include these columns (exact names are flexible - the tool auto-detects):
- `message_id` or `Message ID` - Unique identifier for the message
- `header` or `Header` - Message header text (max 66 chars)
- `body` or `Body` - Message body text (max 144 chars)

Optional columns:
- `image_id` or `Image ID` - Image identifier
- `image_alt_text` or `Alt Text` - Image alt text (max 150 chars)
- `environment` - SANDBOX or PRODUCTION (can be overridden via CLI)

**For Default Configuration (`import-csv-defaults`):**

Required columns:
- `message_id` or `Message ID` - Message identifier
- `locale` or `Locale shortcode` - BCP 47 locale code (e.g., "en-US", "fr-FR")

Optional columns:
- `product_id` or `Product ID` - Can be specified here or via CLI flag

Example CSV structure:
```csv
Message ID,Header,Body,Locale shortcode,Image ID,Alt Text
msg-001,Welcome back!,Check out our new features,en-US,banner-01,Welcome banner
msg-002,Bon retour !,Découvrez nos nouvelles fonctionnalités,fr-FR,banner-01,Bannière de bienvenue
msg-003,おかえりなさい！,新機能をチェック,ja,banner-01,ウェルカムバナー
```

#### Import Messages from CSV

**Basic import with auto-detected columns:**
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action import-csv \
  --csv-file "localizations.csv"
```

**Dry-run to validate before uploading:**
```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action import-csv \
  --csv-file "localizations.csv" \
  --dry-run
```

**Custom column mapping:**

If your CSV uses different column names, specify them explicitly:

```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action import-csv \
  --csv-file "messages.csv" \
  --col-message-id="Message ID" \
  --col-header="Header (Max 66 characters)" \
  --col-body="Body (Max 144 characters)" \
  --col-locale="Locale shortcode"
```

**Verbose output to see column mapping and all rows:**

The `--verbose` flag shows ALL rows with complete field values (works with or without `--dry-run`):

```bash
python retention_message.py \
  --action import-csv \
  --csv-file "localizations.csv" \
  --verbose \
  # ... other params
```

Output:
```
Detected column mapping for SANDBOX environment:
  message_id      <- Sandbox Message ID (fallback: Message ID)
  header          <- Header
  body            <- Body
  locale          <- Locale shortcode
  image_id        <- Sandbox Image ID (fallback: Image ID)
  image_alt_text  <- Alt Text

Target environment: SANDBOX

Fetching existing messages from SANDBOX...
Found 2 existing message(s)

Fetching existing images from SANDBOX...
Found 0 approved image(s)

All rows to be processed:
  Row 2:
    message_id: test-msg-001
    header: "Prevent your files from auto deletion"
    body: "If you decide to cancel, your storage will be limited to 2GB..."
    locale: en-US
    image_id: test-img-001 ⚠ (not found)
    image_alt_text: "Red warning icon"
    → SKIP (already exists)

  Row 3:
    message_id: test-msg-002
    header: "Prevent your files from auto deletion"
    body: "If you decide to cancel, your storage will be limited to 2GB..."
    locale: ar-SA
    image_id: test-img-001 ⚠ (not found)
    image_alt_text: "Red warning icon"
    → UPLOAD (new)

  ... (all 39 rows shown)

Pre-upload Summary:
  Total rows: 39
  Will skip (already exist): 2
  Will attempt upload: 37
  ⚠ Rows with missing images: 37 (uploads will likely fail)

Processing row 37/39 (94.9%)...
```

**Without --verbose flag (default - shows first 3 rows only):**
```bash
python retention_message.py \
  --action import-csv \
  --csv-file "localizations.csv" \
  # ... other params
```

Shows first 3 rows with complete field values, then shows processing progress:
```
Sample of first 3 rows to be processed:
  Row 2:
    message_id: test-msg-001
    header: "Prevent your files from auto deletion"
    body: "If you decide to cancel, your storage will be limited to 2GB..."
    locale: en-US
    → SKIP (already exists)

  ... (showing 3 of 39 rows, use --verbose to see all)

Pre-upload Summary:
  Total rows: 39
  Will skip (already exist): 2
  Will attempt upload: 37

Processing row 37/39 (94.9%)...
```

**Dry-run mode:**
Add `--dry-run` to any of the above commands to validate without uploading:
```bash
python retention_message.py --action import-csv --csv-file data.csv --dry-run --verbose # ... other params
```
Shows "Mode: DRY-RUN (no uploads will be performed)" and skips actual API upload calls.

#### Configure Defaults from CSV

**Import default configurations with CLI product ID:**

Apply the same product ID to all rows in the CSV:

```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action import-csv-defaults \
  --csv-file "localizations.csv" \
  --product-id "com.example.premium"
```

**Import with product_id from CSV column:**

If your CSV includes a `product_id` column, the tool will use it:

```bash
python retention_message.py \
  --key-id "ABCDEFGHIJ" \
  --issuer-id "12345678-1234-1234-1234-123456789012" \
  --bundle-id "com.example.myapp" \
  --p8-file "/path/to/key.p8" \
  --action import-csv-defaults \
  --csv-file "localizations.csv"
```

#### Environment-Aware Column Mapping

The tool supports environment-specific columns to manage both sandbox and production messages in the same CSV file:

**Sandbox-Specific Columns:**
- `Sandbox Message ID` - Used for message_id when `--environment SANDBOX` is specified
- `Sandbox Image ID` - Used for image_id when `--environment SANDBOX` is specified

**Fallback Behavior:**
When operating in SANDBOX environment:
1. If `Sandbox Message ID` column exists and has a value, use it
2. Otherwise, fall back to `Message ID` column
3. Same logic applies for `Sandbox Image ID` vs `Image ID`

When operating in PRODUCTION environment:
- Always uses `Message ID` and `Image ID` columns
- Sandbox-specific columns are ignored

**Example CSV with environment-aware columns:**
```csv
Message ID,Sandbox Message ID,Header,Body,Sandbox Image ID,Image ID
prod-msg-001,test-msg-001,Welcome!,Check out features,test-img-01,prod-img-01
prod-msg-002,test-msg-002,Sale!,50% off today,test-img-02,prod-img-02
```

With this CSV:
- Running with `--environment SANDBOX` uses test-msg-001, test-msg-002, test-img-01, test-img-02
- Running with `--environment PRODUCTION` uses prod-msg-001, prod-msg-002, prod-img-01, prod-img-02

#### Idempotent Behavior

The CSV import is **idempotent** - safe to run multiple times:

**How it works:**
1. Before processing, the tool fetches all existing messages from the target environment
2. Rows with message IDs that already exist are automatically skipped
3. Only new messages are uploaded
4. Results clearly show: successful, skipped, and failed counts

**Benefits:**
- No errors when re-running the same CSV
- Safe to retry after fixing issues in failed rows
- Can incrementally add new messages to existing CSV

**Output example:**
```
Fetching existing messages from SANDBOX...
Found 15 existing message(s)

Pre-upload Summary:
  Total rows: 39
  Will skip (already exist): 15
  Will attempt upload: 24

... processing ...

Results:
  Successful:          22
  Skipped (exist):     15
  Failed:              2
```

#### CSV Import Features

**Progress Reporting:**

The tool shows real-time progress during import:
```
Processing row 25/100 (25.0%)...
```

**Error Recovery:**

If any rows fail, the tool will:
1. Continue processing remaining rows (doesn't stop on first error)
2. Report all successes and failures at the end
3. Export failed rows to a `*_failed.csv` file for easy retry

Example output:
```
============================================================
CSV Import Results - import-csv
============================================================
Total rows processed: 50
Successful:          47
Failed:              3

✓ Successfully processed 47 row(s)

✗ Failed to process 3 row(s):
  Row 12 (msg-012): Header text too long (72 chars). Maximum is 66 characters.
  Row 28 (msg-028): API Error 4090001: Message with this ID already exists
  Row 45 (msg-045): Missing body

Failed rows exported to: localizations_failed.csv
You can fix the issues and re-import this file.
============================================================
```

**Validation:**

The tool validates:
- Required columns are present
- Field length constraints (header ≤66, body ≤144, alt text ≤150)
- Required fields are not empty
- CSV file exists and is readable

**Column Auto-Detection:**

The tool automatically detects common column name patterns (case-insensitive):

| API Field | Detected Patterns |
|-----------|-------------------|
| message_id | "message_id", "message id", "messageid", "id" |
| header | "header", "title" |
| body | "body", "message", "text" |
| locale | "locale", "locale shortcode", "language", "lang" |
| image_id | "image_id", "image id", "imageid", "imageidentifier" |
| image_alt_text | "image_alt_text", "alt text", "alttext", "alt_text" |
| product_id | "product_id", "product id", "productid", "product" |
| environment | "environment", "env" |

#### CSV Import Best Practices

1. **Always use dry-run with verbose first** to validate your CSV without making API calls
   ```bash
   # Review ALL rows before uploading
   python retention_message.py --action import-csv --csv-file data.csv --dry-run --verbose # ... other params
   ```
   This shows exactly what will be uploaded for every row, including which messages already exist and will be skipped.

2. **Verify column mapping** - Check the detected mapping matches your expectations
   - Especially important for sandbox-specific columns
   - Use `--col-<field>` flags if auto-detection is incorrect

3. **Review the pre-upload summary** - Confirms how many messages will be skipped vs uploaded

4. **Start with a small subset** for initial testing if you have a very large CSV

5. **Use consistent column names** across your CSV files to leverage auto-detection

6. **Check the failed CSV** if any rows fail and fix issues before retrying
   - Failed rows are exported to `*_failed.csv`
   - Fix issues and re-import the failed CSV

7. **Keep backups** of your CSV files before bulk operations

8. **Idempotent by default** - Safe to re-run the same command multiple times
   - Existing messages are automatically skipped
   - Only new messages are uploaded

#### CSV Import Use Cases

**Localization Management:**

Manage all localized messages in a single CSV file:

```csv
Message ID,Header,Body,Locale shortcode
welcome-msg,Welcome back!,Check out our new features,en-US
welcome-msg,Bon retour !,Découvrez nos nouvelles fonctionnalités,fr-FR
welcome-msg,Willkommen zurück!,Schauen Sie sich unsere neuen Funktionen an,de-DE
welcome-msg,おかえりなさい！,新機能をチェックしてください,ja
```

Then import all localizations at once:
```bash
python retention_message.py --action import-csv --csv-file localizations.csv # ... other params
```

**Testing Environment Migration:**

Export messages from one environment and import to another (note: you would need to create the CSV manually or via API):

```bash
# Upload to sandbox first
python retention_message.py --action import-csv --csv-file messages.csv --environment SANDBOX # ... other params

# After testing, upload to production
python retention_message.py --action import-csv --csv-file messages.csv --environment PRODUCTION # ... other params
```

**Batch Default Configuration:**

Configure defaults for all locale/product combinations:

```csv
Message ID,Locale shortcode,Product ID
msg-001,en-US,com.example.premium
msg-002,fr-FR,com.example.premium
msg-003,de-DE,com.example.premium
msg-004,ja,com.example.premium
```

```bash
python retention_message.py --action import-csv-defaults --csv-file defaults.csv # ... other params
```

#### CSV Import Limitations

**Current Limitations:**

1. **Cannot Update Existing Messages**
   - The App Store Server API does not support updating/modifying existing messages
   - Once uploaded, a message cannot be changed
   - To modify a message, you must delete it first and re-upload with changes
   - The tool automatically skips existing messages (idempotent behavior)

2. **No Batch API**
   - Messages are uploaded one at a time via individual API calls
   - Large CSVs may take time to process
   - Use `--verbose` to monitor progress

3. **Message State Transitions**
   - Messages go through Apple's review process: PENDING → APPROVED/REJECTED
   - Images also go through review and must be APPROVED before messages can use them
   - You cannot skip the review process
   - Test thoroughly in SANDBOX before uploading to PRODUCTION

4. **Image Validation**
   - The tool automatically fetches and validates image IDs before uploading messages
   - Only APPROVED images can be used in messages
   - Sample output shows ⚠ warnings for missing or non-approved images
   - Pre-upload summary shows count of rows with invalid images
   - This helps catch image errors before wasting time uploading messages

#### Future Enhancements

The following features may be added in future versions:

- **`--force-upload-existing` flag**: Automatically delete and re-upload existing messages to update them
- **`--update-existing` support**: If Apple adds PATCH/UPDATE API support
- **Status column filtering**: Skip rows based on Status column (e.g., only upload if Status is empty or "READY")
- **Parallel uploads**: Upload multiple messages concurrently to speed up large imports
- **CSV export**: Export existing messages to CSV format for backup/migration
- **Diff mode**: Show what would change before uploading

**Workaround for updating existing messages:**

```bash
# 1. First, delete the existing message
python retention_message.py --action delete --message-id msg-001 # ... other params

# 2. Then re-import the CSV (which will now upload the "new" message)
python retention_message.py --action import-csv --csv-file messages.csv # ... other params
```

**Handling Image Errors:**

The tool performs **pre-flight image validation** and will warn you before uploading if images are missing:

```
Pre-upload Summary:
  Total rows: 39
  ⚠ Rows with missing images: 38 (uploads will likely fail)
```

If you see this warning, you have several options:

1. **Option 1: Upload without images**
   - Clear the image_id and image_alt_text columns in your CSV
   - Messages will upload successfully without images
   - You can add images later if needed

2. **Option 2: Upload images first**
   - Upload the images with those IDs to the environment before uploading messages
   - Images must be APPROVED (not just PENDING) for messages to use them
   - For SANDBOX: Ensure "Sandbox Image ID" column has correct IDs
   - For PRODUCTION: Ensure "Image ID" column has correct IDs

3. **Option 3: Use existing image IDs**
   - Update your CSV to use image IDs that already exist and are APPROVED in the environment
   - The tool shows which images exist during the pre-flight check

The sample output shows ⚠ warnings next to image_ids that don't exist, making it easy to spot problems before uploading.

### Environment Options

By default, the tool uses the **SANDBOX** environment. For production:

```bash
python retention_message.py \
  --environment PRODUCTION \
  # ... other parameters
```

### Output Formats

#### Human-Readable (default)
```
✓ Message uploaded successfully!
  Message ID: abc-123-def
  Header: Welcome back!
  Body: Check out our new features
```

#### JSON Format
Use `--json` for programmatic usage:
```bash
python retention_message.py --json --action list # ... other params
```

Output:
```json
{
  "status": "success",
  "messages": [
    {
      "message_id": "abc-123-def",
      "state": "PENDING"
    }
  ],
  "total_count": 1
}
```

### Message States

Messages can be in one of three states:
- **PENDING**: Message uploaded and awaiting Apple's review
- **APPROVED**: Message approved and can be shown to users
- **REJECTED**: Message rejected and cannot be used

### Constraints and Limits

- **Header text**: Maximum 66 characters
- **Body text**: Maximum 144 characters
- **Image alt text**: Maximum 150 characters
- **Message ID**: Must be unique (UUIDs recommended)
- **Total messages**: Limited number per app (see Apple's documentation)

### Error Handling

The tool provides clear error messages for common issues:

| Error Code | Description | Solution |
|------------|-------------|----------|
| 4000023 | Invalid product ID | Verify product ID exists in App Store Connect |
| 4000164 | Invalid locale | Use valid locale code (e.g., "en-US", "fr-FR") |
| 4010001 | Header text too long | Reduce header to ≤66 characters |
| 4010002 | Body text too long | Reduce body to ≤144 characters |
| 4010003 | Alt text too long | Reduce alt text to ≤150 characters |
| 4010004 | Maximum messages reached | Delete old messages first |
| 4030017 | Message not approved | Wait for Apple approval before setting as default |
| 4030018 | Image not approved | Wait for Apple approval of associated image |
| 4040001 | Message not found | Check message ID spelling |
| 4090001 | Message ID already exists | Use a different message ID |

### Security Notes

- **Never commit** your `.p8` private key files to version control
- Store credentials securely (consider using environment variables)
- Use sandbox environment for testing
- Be cautious with production environment operations

### Troubleshooting

1. **"Private key file not found"**
   - Verify the path to your `.p8` file is correct
   - Ensure the file exists and is readable

2. **"Invalid app identifier"**
   - Check that your bundle ID matches exactly
   - Verify the bundle ID is configured in App Store Connect

3. **Authentication errors**
   - Verify your Key ID and Issuer ID are correct
   - Ensure your private key corresponds to the Key ID
   - Check that the key has appropriate permissions

4. **"Message not found" when deleting**
   - List messages first to see available IDs
   - Ensure you're using the correct environment (sandbox vs production)

### Examples for Different Use Cases

#### A/B Testing Messages
```bash
# Upload message A
python retention_message.py --message-id "test-a-v1" \
  --header "Come back!" --body "We miss you" # ... other params

# Upload message B
python retention_message.py --message-id "test-b-v1" \
  --header "New features!" --body "Check out what's new" # ... other params
```

#### Seasonal Campaigns
```bash
# Holiday campaign
python retention_message.py --message-id "holiday-2023" \
  --header "Holiday Sale!" --body "Limited time: 40% off premium" # ... other params

# Back to school
python retention_message.py --message-id "back-to-school-2023" \
  --header "Ready to learn?" --body "New study tools available" # ... other params
```

#### Setting Default Messages Across Multiple Tiers

Apply the same message to all subscription tiers in a single command:

```bash
python retention_message.py \
  --key-id "$KEY_ID" --issuer-id "$ISSUER_ID" \
  --bundle-id "$BUNDLE_ID" --p8-file "$P8_FILE" \
  --action set-default --message-id "general-retention-v1" \
  --product-id "com.example.basic" \
  --product-id "com.example.premium" \
  --product-id "com.example.pro" \
  --locale "en-US"
```

Output for bulk operations:
```
✓ Default message configured successfully for 3 product(s)!
  Environment: SANDBOX
  Message ID: general-retention-v1
  Locale:     en-US
  Products:   com.example.basic, com.example.premium, com.example.pro
```

### Integration with CI/CD

For automated deployments, use JSON output:

```bash
#!/bin/bash
RESULT=$(python retention_message.py --json --action upload \
  --key-id "$KEY_ID" --issuer-id "$ISSUER_ID" \
  --bundle-id "$BUNDLE_ID" --p8-file "$P8_FILE" \
  --header "Auto-deployed message" --body "Latest features")

if echo "$RESULT" | jq -e '.status == "success"' > /dev/null; then
  echo "Message deployed successfully"
  MESSAGE_ID=$(echo "$RESULT" | jq -r '.message_id')
  echo "Message ID: $MESSAGE_ID"
else
  echo "Deployment failed"
  exit 1
fi
```

## Future Tools

This directory is designed to be expanded with additional CLI tools for other App Store Server API functionality as needed.