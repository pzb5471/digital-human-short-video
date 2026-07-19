# Provider setup

Use this reference only while configuring credentials, account capabilities, endpoints, or rate baselines. Recheck linked pages before changing prices because provider plans and APIs change.

## Alibaba Cloud

1. Create least-privilege credentials and a user-owned OSS bucket in the same operating region.
2. Configure the Marketing Engine SDK endpoint as `intelligentcreation.cn-zhangjiakou.aliyuncs.com`.
3. Configure the CosyVoice workspace-specific Beijing endpoint through `DASHSCOPE_WORKSPACE_ID`; use `DASHSCOPE_TTS_ENDPOINT` only for an approved endpoint override.
4. Confirm in the account/contract that digital-human exports are watermark-free, then set `ALIYUN_ME_WATERMARK_FREE_CONFIRMED=true` or the backward-compatible `DHSV_WATERMARK_FREE_CONFIRMED=true`.
5. Copy current prices into deployment rate configuration and rerun `plan`; do not treat documentation examples as live quotes.

Official primary sources:

- [Marketing Engine billing](https://help.aliyun.com/en/me/product-overview/billing-description)
- [Marketing Engine overview](https://help.aliyun.com/en/me/product-overview/platform-profile)
- [Alibaba Cloud digital-human workflow](https://help.aliyun.com/en/ims/user-guide/overview-of-digital-people)
- [CosyVoice workspace HTTP API](https://help.aliyun.com/en/model-studio/voice-clone-design-http-api)
- [CosyVoice Python SDK](https://help.aliyun.com/en/model-studio/voice-clone-design-python-sdk)
- [Alibaba Cloud Python SDK repository](https://github.com/aliyun/alibabacloud-python-sdk)

## HeyGen

1. Create an API key and confirm the account permits the required API resolution and watermark-free export.
2. Set `HEYGEN_WATERMARK_FREE_CONFIRMED=true` or the backward-compatible `DHSV_WATERMARK_FREE_CONFIRMED=true` only after that account-side confirmation.
3. Use HeyGen as an explicit fallback. Generate a new estimate and paid approval; do not reuse the Aliyun approval.
4. Upload local portrait/audio assets and poll the original `video_id`. Result URLs expire; querying the same job returns refreshed URL data.

Official primary sources:

- [HeyGen API reference](https://docs.heygen.com/reference)
- [HeyGen video generation and status guide](https://docs.heygen.com/docs/create-video-archived)

Watermark-free output depends on provider account eligibility and plan configuration. This workflow cannot guarantee eligibility and never removes a watermark after generation.
