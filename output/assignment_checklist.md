# 作业交付核对（2026-10-10）

| 要求 | 当前状态 | 证据与限制 |
|---|---|---|
| 10家以上、官方年报全文 | 满足：12家公司，2024/2025共24份，4,408页 | data/manifest.json；report_accuracy_audit.md。官方PDF、身份与SHA已核对，PDF通过下载脚本获取、不进仓库。 |
| 提取文字、表格按行列还原、带公司/章节/页码 | 已实现并回归；存在识别限制 | extraction_v4_audit.json：23,620块，17,872表格块；72项关键金额、169处已识别续表首行通过。5,912表格块表头未确认，不等于均错误，也不能声称全库准确。 |
| 向量+BM25、问答页面、答案带出处 | 本机满足；云端尚未上线 | 本地BGE向量512维、BM25、RRF。页面显示引用、块ID、章节、PDF页码和官方原文。默认只检索；本地授权生成或访客自带API key。 |
| 10题、至少2道跨公司全景、逐题召回/正确性/错误 | 满足：v4实际10题，2道12公司全景 | evaluation_v4/；evaluation_records_v4.md；manual_review_v4.json。人工10/10，自动9/10；Q03为约数精度漏判。固定开发题，不是独立测试集。v3共42份结果及失败保留。 |
| 一页结论PDF+页面截图 | 已生成并视觉检查 | pdf/conclusion.pdf；screenshots/v4_submission_single.png、v4_submission_panorama.png。 |
| 代码仓库地址及三行提交文本 | 已上传GitHub并验证远端提交 | submission.txt已填写https://github.com/1095148297qq-cell/financial-rag；代码已推送main，远端与本地提交一致。 |
| 前端Vercel | 可部署文件已准备；尚未部署 | 根目录vercel.json；DEPLOYMENT.md。不配置后端仅展示已保存评测，不具备公网实时检索。 |
| 密钥及个人授权不进仓库 | 候选文件与构建产物扫描通过 | deployment_security_check.json；公开后端不允许调用作者本地授权。 |

## 复核与已知限制

10项后端/表头/权限测试通过；真实HTTP检索12项通过；10份当前评测、旧失败案例切换、JSON导出和手机布局通过。评测原始回答没有改写。更新回答或证据后，必须重新人工复核；交付生成器校验已复核证据指纹，避免沿用旧评分。

用户已提供GitHub空仓库。上传时如浏览器要求登录授权，由用户在官方页面完成。Vercel导入仓库需要用户账户。付费后端未创建，费用和平台另行确认；本机无Docker，Linux镜像尚未实际构建和HTTPS联调。
