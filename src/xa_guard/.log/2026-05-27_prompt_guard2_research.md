## 2026-05-27 Prompt Guard 2 调研日志

调研 Meta Llama Prompt Guard 2，重点核查中文支持、微调需求、竞品对比。
结论：86M 版本基于 mDeBERTa 理论上支持中文，但官方未公布中文 benchmark；
中文政企场景需微调，成本中等。推荐备选：Qwen3Guard-Gen-8B（中文原生），
ProtectAI deberta-v3-base-prompt-injection-v2（轻量可 CPU）。
无现成中文微调版 Prompt Guard 2，Arabic 微调版可作参考路径。
