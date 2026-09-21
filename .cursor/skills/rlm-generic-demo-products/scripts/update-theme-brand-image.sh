#!/usr/bin/env bash
# update-theme-brand-image.sh
# Resizes a company logo to 600x120 (contain + pad), uploads it as a Salesforce
# ContentAsset via REST, and replaces BRAND_IMAGE on the active Lightning theme
# QuantumBitSLDSv2 (Setup → Themes and Branding).
#
# Usage:
#   bash scripts/update-theme-brand-image.sh <imagePath> <assetName> <orgUsername>
#
# Arguments:
#   imagePath    - Absolute or relative path to the local logo (JPG/PNG/GIF).
#   assetName    - ContentAsset developer name (alphanumeric + underscores only,
#                  must start with a letter, max 40 characters — sanitize before
#                  calling this script, e.g. AcmeCorp_BrandLogo)
#   orgUsername  - Salesforce username or alias. Optional if SF_TARGET_ORG is set.
#                  Required one way or the other — this project is not an SFDX
#                  workspace, so the CLI default org must not be used silently.
#
# Requirements:
#   - sf CLI authenticated to the target org
#   - python3 (standard on macOS/Linux)
#   - Pillow (`pip3 install pillow`) OR macOS `sips` for resize
#
# Why REST (not sf project deploy start --metadata):
#   The metadata deploy path requires an SFDX project scaffold (sfdx-project.json +
#   force-app/...) and does not reliably package binary files. This REST approach
#   needs no project scaffold and is idempotent (new ContentVersion on re-run).
#
# Why Python (not curl):
#   curl fails for large images because the base64-encoded body exceeds shell
#   argument length limits. Python handles the payload in-process.

set -euo pipefail

IMAGE_PATH="${1:?Usage: $0 <imagePath> <assetName> <orgUsername>}"
ASSET_NAME="${2:?Usage: $0 <imagePath> <assetName> <orgUsername>}"
TARGET_ORG="${3:-${SF_TARGET_ORG:-}}"
THEME_DEVELOPER_NAME="QuantumBitSLDSv2"

if [[ -z "$TARGET_ORG" ]]; then
  echo "ERROR: Target org is required." >&2
  echo "       Pass username/alias as the third argument, or set SF_TARGET_ORG." >&2
  echo "       Usage: $0 <imagePath> <assetName> <orgUsername>" >&2
  exit 1
fi

if [[ ! "$ASSET_NAME" =~ ^[A-Za-z][A-Za-z0-9_]{0,39}$ ]]; then
  echo "ERROR: Asset name '$ASSET_NAME' is invalid." >&2
  echo "       Use alphanumeric characters and underscores only, start with a letter," >&2
  echo "       and keep length at 40 characters or fewer." >&2
  exit 1
fi

if [[ ! -f "$IMAGE_PATH" ]]; then
  echo "ERROR: Image file not found: $IMAGE_PATH" >&2
  exit 1
fi

EXT="${IMAGE_PATH##*.}"
EXT_LOWER=$(printf '%s' "$EXT" | tr '[:upper:]' '[:lower:]')
case "$EXT_LOWER" in
  png|jpg|jpeg|gif) ;;
  *)
    echo "ERROR: Brand Image must be JPG, PNG, or GIF (got '.$EXT_LOWER')." >&2
    echo "       Salesforce Themes and Branding does not accept SVG." >&2
    exit 1
    ;;
esac

echo "Fetching org credentials for $TARGET_ORG..."
ORG_JSON=$(sf org display --target-org "$TARGET_ORG" --json)
INSTANCE_URL=$(echo "$ORG_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['instanceUrl'])")
# sf org display redacts accessToken; use dedicated auth command
ACCESS_TOKEN=$(sf org auth show-access-token --target-org "$TARGET_ORG" --json | python3 -c "import sys,json; d=json.load(sys.stdin); print((d.get('result') or {}).get('accessToken') or d.get('accessToken') or '')")
API_VERSION=$(echo "$ORG_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'].get('apiVersion','66.0'))")
ORG_USERNAME=$(echo "$ORG_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'].get('username',''))")
ORG_ID=$(echo "$ORG_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'].get('id',''))")

if [[ -z "$INSTANCE_URL" || -z "$ACCESS_TOKEN" ]]; then
  echo "ERROR: Could not retrieve org credentials for '$TARGET_ORG'." >&2
  echo "       Authenticate with: sf org login web --alias <alias>" >&2
  exit 1
fi

TMP_PNG=$(mktemp "${TMPDIR:-/tmp}/brand-logo-XXXXXX.png")
trap 'rm -f "$TMP_PNG"' EXIT

echo "Org username: $ORG_USERNAME"
echo "Org Id: $ORG_ID"
echo "Org: $INSTANCE_URL"
echo "Theme: $THEME_DEVELOPER_NAME"
echo "Resizing logo to 600x120 (contain + pad)..."

python3 - "$IMAGE_PATH" "$ASSET_NAME" "$TMP_PNG" "$INSTANCE_URL" "$ACCESS_TOKEN" "$API_VERSION" "$THEME_DEVELOPER_NAME" <<'PYEOF'
import base64, json, os, shutil, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

src_path, asset_name, dest_png, instance_url, access_token, api_version, theme_name = sys.argv[1:]
TARGET_W, TARGET_H = 600, 120
MAX_BYTES = 5 * 1024 * 1024
AUTH = {"Authorization": f"Bearer {access_token}"}


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def rest_json(url, method="GET", payload=None, extra_headers=None, fatal=True):
    headers = dict(AUTH)
    data = None
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        msg = f"HTTP {e.code} {method} {url}: {e.read().decode()}"
        if fatal:
            die(msg)
        print(f"WARNING: {msg}", file=sys.stderr)
        return None


def query(soql, tooling=False):
    path = "tooling/query" if tooling else "query"
    url = f"{instance_url}/services/data/v{api_version}/{path}?q={urllib.parse.quote(soql)}"
    return rest_json(url)


def resize_pillow(src, dest):
    from PIL import Image

    resample = Image.LANCZOS
    if hasattr(Image, "Resampling"):
        resample = Image.Resampling.LANCZOS
    img = Image.open(src)
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA") if has_alpha else img.convert("RGB")
    img.thumbnail((TARGET_W, TARGET_H), resample)
    if has_alpha:
        canvas = Image.new("RGBA", (TARGET_W, TARGET_H), (255, 255, 255, 0))
        canvas.paste(img, ((TARGET_W - img.width) // 2, (TARGET_H - img.height) // 2), img)
    else:
        canvas = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
        canvas.paste(img, ((TARGET_W - img.width) // 2, (TARGET_H - img.height) // 2))
    canvas.save(dest, "PNG")


def parse_sips_dim(output, key):
    for line in output.splitlines():
        if key in line:
            return int(line.split()[-1])
    return None


def resize_sips(src, dest):
    if not shutil.which("sips"):
        raise RuntimeError("sips not found")
    probe = subprocess.check_output(["sips", "-g", "pixelWidth", "-g", "pixelHeight", src], text=True)
    width = parse_sips_dim(probe, "pixelWidth")
    height = parse_sips_dim(probe, "pixelHeight")
    if not width or not height:
        raise RuntimeError(f"Could not read image dimensions via sips:\n{probe}")
    scale = min(TARGET_W / width, TARGET_H / height)
    new_w = max(1, round(width * scale))
    new_h = max(1, round(height * scale))
    subprocess.check_call(["sips", "-z", str(new_h), str(new_w), src, "--out", dest], stdout=subprocess.DEVNULL)
    if new_w != TARGET_W or new_h != TARGET_H:
        subprocess.check_call(
            ["sips", "--padToHeightWidth", str(TARGET_H), str(TARGET_W), "--padColor", "FFFFFF", dest],
            stdout=subprocess.DEVNULL,
        )


def resize_logo(src, dest):
    try:
        resize_pillow(src, dest)
        print("Resized with Pillow.")
        return
    except ImportError:
        pass
    except Exception as exc:
        print(f"Pillow resize failed ({exc}); trying sips...", file=sys.stderr)
    try:
        resize_sips(src, dest)
        print("Resized with sips.")
        return
    except Exception as exc:
        die(
            "Could not resize the logo to 600x120. Install Pillow and retry:\n"
            f"       pip3 install pillow\n"
            f"       ({exc})"
        )


resize_logo(src_path, dest_png)
file_size = os.path.getsize(dest_png)
if file_size > MAX_BYTES:
    die(f"Resized logo is {file_size} bytes; Brand Image must be smaller than 5 MB.")
print(f"Resized logo: {dest_png} ({file_size} bytes)")

with open(dest_png, "rb") as f:
    encoded = base64.b64encode(f.read()).decode("utf-8")

theme = query(
    f"SELECT Id, DeveloperName, DefaultBrandingSetId FROM LightningExperienceTheme "
    f"WHERE DeveloperName='{theme_name}'",
    tooling=True,
)
if theme.get("totalSize", 0) == 0:
    die(
        f"LightningExperienceTheme '{theme_name}' was not found. "
        "From Setup → Themes and Branding, the active record Developer Name must be QuantumBitSLDSv2."
    )
branding_set_id = theme["records"][0].get("DefaultBrandingSetId")
if not branding_set_id:
    die(f"Theme '{theme_name}' has no DefaultBrandingSetId.")
print(f"Theme Id: {theme['records'][0]['Id']}")
print(f"BrandingSet Id: {branding_set_id}")

existing_asset = query(
    f"SELECT Id, DeveloperName, ContentDocumentId FROM ContentAsset WHERE DeveloperName='{asset_name}'"
)
cv_url = f"{instance_url}/services/data/v{api_version}/sobjects/ContentVersion"
path_on_client = f"{asset_name}.png"
actual_asset_name = asset_name

if existing_asset.get("totalSize", 0) > 0:
    content_document_id = existing_asset["records"][0]["ContentDocumentId"]
    content_asset_id = existing_asset["records"][0]["Id"]
    print(f"ContentAsset '{asset_name}' exists ({content_asset_id}); uploading a new version...")
    created = rest_json(
        cv_url,
        method="POST",
        payload={
            "ContentDocumentId": content_document_id,
            "PathOnClient": path_on_client,
            "Title": asset_name,
            "ReasonForChange": "Replace org Brand Image with researched company logo",
            "VersionData": encoded,
        },
    )
else:
    print(f"Creating ContentAsset '{asset_name}' (IsAssetEnabled=true)...")
    created = rest_json(
        cv_url,
        method="POST",
        payload={
            "Title": asset_name,
            "PathOnClient": path_on_client,
            "VersionData": encoded,
            "IsAssetEnabled": True,
        },
    )
    content_version_id = created.get("id")
    if not content_version_id:
        die(f"ContentVersion create did not return an Id: {created}")
    cv = query(
        f"SELECT Id, ContentDocumentId, VersionNumber FROM ContentVersion "
        f"WHERE Id='{content_version_id}' AND IsLatest=true"
    )
    if cv.get("totalSize", 0) == 0:
        die(f"Could not re-query ContentVersion {content_version_id}.")
    content_document_id = cv["records"][0]["ContentDocumentId"]
    content_asset = None
    for _ in range(10):
        found = query(
            f"SELECT Id, DeveloperName, ContentDocumentId FROM ContentAsset "
            f"WHERE ContentDocumentId='{content_document_id}'"
        )
        if found.get("totalSize", 0) > 0:
            content_asset = found["records"][0]
            break
        time.sleep(0.5)
    if not content_asset:
        die("ContentVersion was created with IsAssetEnabled=true but ContentAsset was not found.")
    content_asset_id = content_asset["Id"]
    actual_asset_name = content_asset.get("DeveloperName") or asset_name
    patch_body = {"IsVisibleByExternalUsers": True}
    if actual_asset_name != asset_name:
        patch_body.update({"DeveloperName": asset_name, "MasterLabel": asset_name})
    patched = rest_json(
        f"{instance_url}/services/data/v{api_version}/sobjects/ContentAsset/{content_asset_id}",
        method="PATCH",
        payload=patch_body,
        fatal=False,
    )
    if patched is not None and actual_asset_name != asset_name:
        actual_asset_name = asset_name
        print(f"Updated ContentAsset DeveloperName to '{asset_name}'.")
    elif patched is None and actual_asset_name != asset_name:
        print(f"Using org ContentAsset DeveloperName '{actual_asset_name}' for BRAND_IMAGE.")

latest = query(
    f"SELECT Id, VersionNumber FROM ContentVersion "
    f"WHERE ContentDocumentId='{content_document_id}' AND IsLatest=true"
)
if latest.get("totalSize", 0) == 0:
    die("Could not read latest ContentVersion for the brand-image asset.")
version_number = latest["records"][0]["VersionNumber"]
property_value = f"/file-asset/{actual_asset_name}?v={version_number}"
print(f"BRAND_IMAGE value: {property_value}")

prop = query(
    f"SELECT Id, PropertyName, PropertyValue FROM BrandingSetProperty "
    f"WHERE BrandingSetId='{branding_set_id}' AND PropertyName='BRAND_IMAGE'",
    tooling=True,
)
tooling_prop = f"{instance_url}/services/data/v{api_version}/tooling/sobjects/BrandingSetProperty"
if prop.get("totalSize", 0) > 0:
    prop_id = prop["records"][0]["Id"]
    rest_json(
        f"{tooling_prop}/{prop_id}",
        method="PATCH",
        payload={"PropertyValue": property_value},
    )
    print(f"Updated BrandingSetProperty {prop_id} (replaced existing Brand Image).")
else:
    created_prop = rest_json(
        tooling_prop,
        method="POST",
        payload={
            "BrandingSetId": branding_set_id,
            "PropertyName": "BRAND_IMAGE",
            "PropertyValue": property_value,
        },
    )
    print(f"Created BrandingSetProperty {created_prop.get('id')} (BRAND_IMAGE was missing).")

print(f"SUCCESS: Theme '{theme_name}' Brand Image is now {property_value}")
print(f"         ContentAsset Id: {content_asset_id}")
PYEOF
