# Provider setup

Use this reference only while configuring credentials, account capabilities, endpoints, or rate baselines. Recheck linked pages before changing prices because provider plans and APIs change. Pricing links below were last verified on `2026-07-19`; also check the provider billing console and record the date used for each approval.

## Alibaba Cloud

1. Create least-privilege credentials and a user-owned OSS bucket in the same operating region.
2. Configure the Marketing Engine SDK endpoint as `intelligentcreation.cn-zhangjiakou.aliyuncs.com`.
3. Set `ALIYUN_ANCHOR_GENDER=M` or `ALIYUN_ANCHOR_GENDER=F` to match the authorized portrait; photo-anchor creation rejects other values.
4. Configure the CosyVoice workspace-specific Beijing endpoint through `DASHSCOPE_WORKSPACE_ID`; use `DASHSCOPE_TTS_ENDPOINT` only for an approved endpoint override.
5. Confirm in the account/contract that digital-human exports are watermark-free, then set `ALIYUN_ME_WATERMARK_FREE_CONFIRMED=true` or the backward-compatible `DHSV_WATERMARK_FREE_CONFIRMED=true`.
6. Copy current prices into `DHSV_ALIYUN_CNY_PER_MINUTE` and `DHSV_COSYVOICE_CNY_PER_1000_CHARACTERS`, then rerun `plan`; do not treat documentation examples as live quotes.

Official primary sources:

- [Marketing Engine billing](https://help.aliyun.com/en/me/product-overview/billing-description)
- [Model Studio pricing, including CosyVoice](https://help.aliyun.com/en/model-studio/model-pricing)
- [Marketing Engine overview](https://help.aliyun.com/en/me/product-overview/platform-profile)
- [Digital human offline synthesis OpenAPI](https://help.aliyun.com/en/me/getting-started/digital-human-offline-synthesis-openapi)
- [Alibaba Cloud digital-human workflow](https://help.aliyun.com/en/ims/user-guide/overview-of-digital-people)
- [CosyVoice workspace HTTP API](https://help.aliyun.com/en/model-studio/voice-clone-design-http-api)
- [CosyVoice Python SDK](https://help.aliyun.com/en/model-studio/voice-clone-design-python-sdk)
- [Alibaba Cloud Python SDK repository](https://github.com/aliyun/alibabacloud-python-sdk)

## HeyGen

1. Create an API key and confirm the account permits the required API resolution and watermark-free export.
2. Set `HEYGEN_WATERMARK_FREE_CONFIRMED=true` or the backward-compatible `DHSV_WATERMARK_FREE_CONFIRMED=true` only after that account-side confirmation.
3. Use HeyGen only after the user explicitly chooses it. Change the project provider to `heygen`, set the current `DHSV_HEYGEN_USD_PER_SECOND`, rerun `plan`, and obtain a new approval for the new provider/currency/amount; do not reuse the Aliyun approval.
4. Prefer `HEYGEN_AVATAR_ID` or a cached avatar. With neither available, the adapter fails before uploading the portrait unless `HEYGEN_IMAGE_FALLBACK=true` was explicitly chosen; empty, `false`, and other values keep fallback disabled.
5. Upload local portrait/audio assets and poll the original `video_id`. Result URLs expire; querying the same job returns refreshed URL data.

Official primary sources:

- [HeyGen API reference](https://docs.heygen.com/reference)
- [HeyGen pricing](https://www.heygen.com/pricing)

Watermark-free output depends on provider account eligibility and plan configuration. This workflow cannot guarantee eligibility and never removes a watermark after generation.

Never recharge, buy credits, enable auto-reload, subscribe, or upgrade a plan without separate explicit user authorization. A video estimate approval authorizes only the matching paid generation tuple.
