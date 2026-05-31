# backends 工作日志

## 2026-05-31

为 LlamaGuard 后端添加 TODO 标注，提醒后续开发者在启用前必须细化分类映射。
- `llamaguard.py`：在 `DEFAULT_CATEGORY_MAP` 上方添加 TODO 注释，说明 S1-S14 应映射到不同 XA-Guard 类别（如 shell_dangerous、pii_leak、political_sensitive），而非全部折叠为 unsafe。
- `policies/llamaguard_category_map.yaml`：文件顶部添加详细 TODO 注释头，列出 Meta Llama Guard 3 的 14 个安全类别及其含义，并说明需对齐 XA-Guard 统一分类后方可上线。
- `configs/xa-guard.yaml`：在注释掉的 model_llamaguard 块上方添加 TODO 行，提示先完善 category_map 再启用。
