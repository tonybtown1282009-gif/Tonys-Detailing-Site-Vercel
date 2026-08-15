/**
 * Tony's Detailing — Google Sheets backup for booking submissions.
 *
 * Deploy this as a Google Apps Script Web App and paste its /exec URL into the
 * Vercel env var SHEETS_WEBHOOK_URL. The Flask app POSTs each booking here as
 * JSON (see send_to_sheets_webhook in app.py); this appends one row per booking.
 *
 * Setup steps live in README.md ("Google Sheets backup").
 */

// Column order for the sheet. The first entry is a server-side receipt time;
// the rest mirror the JSON payload keys sent by app.py. Add new fields to the
// END of this list so existing columns keep their position.
var HEADERS = [
  'received_at',
  'timestamp',
  'name',
  'phone',
  'email',
  'location',
  'num_vehicles',
  'vehicle_type',
  'service',
  'addons',
  'upcharges',
  'expecting_discount_1',
  'vehicle_type_2',
  'service_2',
  'addons_2',
  'upcharges_2',
  'expecting_discount_2',
  'referred_by',
  'discount_applied',
  'total_estimate',
  'visits',
  'notes'
];

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000); // serialize concurrent submissions so rows don't collide
  try {
    var data = JSON.parse((e && e.postData && e.postData.contents) || '{}');

    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];

    // Write a header row once, on the first booking into an empty sheet.
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(HEADERS);
    }

    var row = HEADERS.map(function (key) {
      if (key === 'received_at') {
        return new Date();
      }
      var value = data[key];
      if (value === undefined || value === null) {
        return '';
      }
      if (value === true) {
        return 'Yes';
      }
      if (value === false) {
        return '';
      }
      return value;
    });

    sheet.appendRow(row);

    return ContentService
      .createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}
