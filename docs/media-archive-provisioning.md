# Provisioning Cloudflare R2 (~10 minutes, one time)

You need a Cloudflare account and a payment card on file. R2 has a free tier (10 GB storage, generous ops) and costs about **€1/month per 50 GB** beyond it, with **no egress charge ever**.

## 1. Create the bucket

1. Cloudflare dashboard → **R2** → *Create bucket*.
2. Name it `slow-interpolation-media`. Location: *Automatic* is fine.
3. Leave public access **OFF**. This is the private master; default-private is the whole posture.

## 2. Create the S3 API token

1. R2 → **Manage R2 API Tokens** → *Create API token*.
2. Permission: **Object Read & Write**.
3. Scope it to **this bucket only** (not "all buckets") — least privilege.
4. Submit. The result screen shows, **once**:
   - **Access Key ID** → `R2_ACCESS_KEY_ID`
   - **Secret Access Key** → `R2_SECRET_ACCESS_KEY`
   - the endpoint `https://<hex>.r2.cloudflarestorage.com` → the hex part is `R2_ACCOUNT_ID`

   Copy all three now. The secret is not shown again — if you lose it, delete the token and make a new one.

   > The **token value** displayed alongside is *not* the same thing as the S3 credentials. Using it produces `InvalidAccessKeyId`.

## 3. Fill in `tools/.env`

```
R2_ACCOUNT_ID=<the hex from the endpoint URL>
R2_ACCESS_KEY_ID=<S3 Access Key ID>
R2_SECRET_ACCESS_KEY=<S3 Secret Access Key>
R2_BUCKET=slow-interpolation-media
```

Then:

```
py -3.11 tools/media_archive_verify.py
```

That does a real round-trip (upload → sha verify → download → compare → delete). It must print **READY** before you ingest anything.

## 4. Captioning key (optional, recommended)

Get a Gemini API key from Google AI Studio and add `GEMINI_API_KEY=` to `tools/.env`. Without it ingest still uploads, checksums, dedupes, thumbnails and catalogues — assets simply arrive with no caption and no scene tags, which makes search much weaker. Budget roughly **€1-3 per 3,000 images**.

## 5. Public bucket (optional, only when you need permanent public links)

Skip this until someone actually asks for a shareable link.

1. Create a second bucket `slow-interpolation-media-public`.
2. Enable public access on it — either the `r2.dev` development URL (rate-limited, fine for occasional use) or, better, a **custom domain** (routes through the Cloudflare CDN, so repeated reads are cached).
3. Create a second API token, **Object Read & Write scoped to the public bucket only**.
4. Add to `tools/.env`:
   ```
   R2_PUBLIC_BUCKET=slow-interpolation-media-public
   R2_PUBLIC_ACCESS_KEY_ID=...
   R2_PUBLIC_SECRET_ACCESS_KEY=...
   R2_PUBLIC_DEV_URL=https://pub-xxxxxxxx.r2.dev      # or https://media.yourdomain.com
   ```

Custom domain caveat: the domain's DNS zone must be reachable in Cloudflare. If the domain is registered elsewhere, a **partial (CNAME) setup for just the `media.` subdomain** is enough — no need to move nameservers.

## Common errors and what they actually mean

| Error | Cause |
|---|---|
| `InvalidAccessKeyId` | You used the API *token value* instead of the S3 Access Key ID. |
| `SignatureDoesNotMatch` | Wrong secret, or the machine clock is skewed. Check both. |
| `AccessDenied` | The token isn't scoped to this bucket, or is read-only. |
| `NoSuchBucket` / `404` | `R2_BUCKET` doesn't match exactly, or `R2_ACCOUNT_ID` is wrong. |

`media_store.py` maps these to a plain-English fix at runtime, so you rarely have to look them up.
