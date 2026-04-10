---
name: pdf-to-feishu
description: 将 PDF 论文翻译为中文并写入飞书知识库，保持原文格式，图片放在原位置
user_invocable: true
---

# PDF 论文翻译写入飞书知识库

将一篇 PDF 论文（通常为英文学术论文）翻译为中文，并写入用户指定的飞书知识库页面下，保持原论文格式，图片插入原位置。

## 输入信息

用户需要提供以下信息（如果未提供则主动询问）：

1. **PDF 文件路径** - 论文 PDF 的本地路径
2. **飞书 App ID 和 App Secret** - 飞书开放平台应用凭证（已保存在记忆中则无需再次提供）
3. **目标知识库 URL 或父节点 token** - 飞书知识库中的目标位置
4. **文档标题**（可选）- 如不提供则从论文标题翻译生成

## 工作流程

### Step 1: 准备工作
- 检查 PyMuPDF 是否安装：`pip3 install PyMuPDF -q`
- 确认 Pillow 已安装

### Step 2: 读取 PDF 内容
- 使用 Read 工具逐页读取 PDF（每次最多 20 页）
- 记录论文的完整结构：标题、摘要、各章节、图表位置
- 特别标注每个图表（Figure/Table）所在的页码和大致位置（左列/右列/全宽/上方/下方）

### Step 3: 获取飞书 Access Token
```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal' \
  -H 'Content-Type: application/json' \
  -d '{"app_id":"<APP_ID>","app_secret":"<APP_SECRET>"}'
```

### Step 4: 获取知识库空间信息
从 URL 中提取 node_token（URL 路径中 `/wiki/` 后面的部分），然后：
```bash
curl -s -X GET 'https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token=<NODE_TOKEN>' \
  -H 'Authorization: Bearer <TOKEN>'
```
从返回结果获取 `space_id`。

### Step 5: 创建知识库文档节点
```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/wiki/v2/spaces/<SPACE_ID>/nodes' \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{"obj_type":"docx","node_type":"origin","parent_node_token":"<PARENT_TOKEN>","title":"<TITLE>"}'
```
**必须传 `node_type: "origin"`**，否则报 field validation failed。
返回的 `obj_token` 即为 `document_id`，同时也是根 block_id。

### Step 6: 从 PDF 提取图片

采用**混合策略**——照片用 pdfimages 提取原始素材，图表用 PyMuPDF 渲染裁剪：

| 图片类型 | 工具 | 原因 |
|---|---|---|
| 照片（机器人、任务场景） | `pdfimages` | 提取 PDF 嵌入的原始高清照片，无需裁剪 |
| 图表（柱状图、折线图） | PyMuPDF 渲染 + 裁剪 | 矢量绘制，pdfimages 无法提取 |
| 架构图（流程图、框图） | PyMuPDF 渲染 + 裁剪 | 包含矢量元素和文字标签 |

**6a. 用 pdfimages 提取照片类图片：**
```bash
# 列出 PDF 中所有嵌入图片的信息（页码、尺寸、格式）
pdfimages -list paper.pdf

# 提取所有图片为 PNG（-p 在文件名中包含页码）
pdfimages -png -p paper.pdf output_dir/img
```
提取后会得到大量碎片图片（一篇论文可能有 300+ 张）。需要：
- 按文件大小排序（`ls -lS`），大文件通常是完整的照片行/照片组
- 用 Read 工具逐张查看，识别哪些对应论文中的哪个 Figure
- 注意：同一个 Figure 的多行照片可能被提取为多个独立图片，可用 Pillow 拼接
- smask 文件（透明度遮罩）通常可忽略

**6b. 用 PyMuPDF 渲染页面（用于图表和架构图）：**
```python
import fitz
doc = fitz.open(pdf_path)
for page_num in range(len(doc)):
    page = doc[page_num]
    mat = fitz.Matrix(2, 2)  # 2x 分辨率，页面变为约 1224x1584 像素
    pix = page.get_pixmap(matrix=mat)
    pix.save(f"figures/page_{page_num+1}.png")
```

**6b. 用像素扫描法精确定位图表区域：**

不要凭目测估坐标！必须用 numpy 扫描像素来精确确定图表边界：

```python
import numpy as np
from PIL import Image

img = Image.open("figures/page_X.png")
arr = np.array(img)

# 逐行扫描，找内容区域的起止 y 坐标
for y in range(0, arr.shape[0], 5):
    nw = np.sum(np.any(arr[y, x_start:x_end, :3] < 240, axis=1))
    if nw > 10:
        print(f"y={y}: non_white={nw}")
```

标准两栏论文在 2x 渲染下的参考坐标：
- 页面尺寸：约 1224 x 1584
- 左栏：x 约 30-612
- 右栏：x 约 612-1194

**关键经验：**
- 作者名、标题等文字在 2x 渲染下可能占很大 y 范围（6 行作者名可以从 y=140 一直到 y=410）
- 文字和图表之间的空白间隙通常只有 10-30 像素
- 反锯齿灰色像素（值 200-250）容易被忽略，阈值用 `<240` 比较安全
- 图表标签文字（如 "π cross-embodiment"）属于图表的一部分，不要裁掉

**6c. 裁剪后逐张保存小片段验证（不能只看缩略图！）：**

Read 工具显示的缩略图太小，可能看不清是否有残留文字。对关键图片（特别是图1这种紧邻作者名的），**裁剪顶部/底部 50-80px 单独保存查看**：

```python
# 验证顶部是否有残留文字
top_strip = cropped_image.crop((0, 0, width, 80))
top_strip.save("fig1_top_check.png")
# 用 Read 工具单独查看这个小图
```

**常见裁剪错误：**
- 图1 紧邻作者名/URL，很容易裁入文字 → 必须用像素扫描找到空白间隙
- 饼图/图表区域裁到了旁边的正文文字 → x 或 y 坐标偏了
- 多行子图（如 2x3 网格图表）只截到上半部分 → 用像素扫描找到最后一行内容的 y 坐标
- 图表右侧有标注（如 "s" 标签）被截 → 需要扫描 x 方向找到最右侧内容
- 图表底部 x 轴标签被截 → 需要扫描找最后有内容的 y

### Step 7: 写入文档内容

按论文结构分批写入，每批包含文字段落和对应位置的图片。每个 part 写完后 `time.sleep(0.5)` 防止频率限制。

**写入文字块**（可批量）：
```bash
POST /open-apis/docx/v1/documents/<DOC_ID>/blocks/<DOC_ID>/children
Body: {"children": [<block1>, <block2>, ...]}
```

**插入图片（三步流程，不可批量！）：**

Step 7a - 创建空 Image Block：
```bash
POST /open-apis/docx/v1/documents/<DOC_ID>/blocks/<DOC_ID>/children
Body: {"children": [{"block_type": 27, "image": {}}]}
```
返回 `block_id`（Image BlockID）。

Step 7b - 以 Image BlockID 为 parent_node 上传图片素材：
```bash
POST /open-apis/drive/v1/medias/upload_all
Form-data: file=@image.png, file_name=xx.png, parent_type=docx_image, parent_node=<IMAGE_BLOCK_ID>, size=<SIZE>
```
返回 `file_token`。

Step 7c - 更新 Image Block 设置图片：
```bash
PATCH /open-apis/docx/v1/documents/<DOC_ID>/blocks/<IMAGE_BLOCK_ID>
Body: {"replace_image": {"token": "<FILE_TOKEN>"}}
```

每张图片三步之间各 sleep 0.4 秒。

### Step 8: 修正图片（如有错误）

如果发现某张图裁剪有误需要替换：
1. 重新裁剪正确的图片
2. 用已存在的 Image Block ID 作为 parent_node 重新上传
3. 用 PATCH replace_image 替换

**无需删除重建 Block**，直接对已有 Block 重新上传+patch 即可。

### Step 9: 删除多余内容

如果文档中有多余的测试块或错误内容，使用 batch_delete：
```bash
DELETE /open-apis/docx/v1/documents/<DOC_ID>/blocks/<PARENT_BLOCK_ID>/children/batch_delete
Body: {"start_index": 0, "end_index": 2}
```
start_index/end_index 是子块在父块 children 中的索引范围（左闭右开）。

## Block 类型速查

| block_type | 字段名 | 说明 |
|---|---|---|
| 2 | `text` | 文本段落 |
| 3 | `heading1` | 一级标题 |
| 4 | `heading2` | 二级标题 |
| 5 | `heading3` | 三级标题 |
| 22 | `divider` | 分割线（传空 `{}`） |
| 27 | `image` | 图片（创建时传空 `{}`，不可直接传 token） |

文本/标题 Block 的 elements 数组可以混合 `text_run` 和 `equation` 两种元素：

```json
{
  "block_type": 2,
  "text": {
    "elements": [
      {
        "text_run": {
          "content": "损失函数定义为：",
          "text_element_style": {
            "bold": false, "italic": false,
            "strikethrough": false, "underline": false, "inline_code": false
          }
        }
      },
      {
        "equation": {
          "content": "L^{\\tau}(\\theta) = \\mathbb{E} \\| \\mathbf{v}_{\\theta} - \\mathbf{u} \\|^2"
        }
      },
      {
        "text_run": {
          "content": "，其中...",
          "text_element_style": {}
        }
      }
    ],
    "style": {}
  }
}
```

### 公式排版规则

**行内公式**：在 `elements` 数组中混合 `text_run` 和 `equation` 元素，公式自然嵌入文字中。

**独立居中公式**：创建一个只包含 `equation` 元素的段落，设置 `"style": {"align": 2}` 居中：
```json
{
  "block_type": 2,
  "text": {
    "elements": [
      {"equation": {"content": "\\mathbf{A}_t^{\\tau+\\delta} = \\mathbf{A}_t^{\\tau} + \\delta \\mathbf{v}_{\\theta}"}}
    ],
    "style": {"align": 2}
  }
}
```

**公式中使用 LaTeX 语法**，常用符号：
- 粗体向量：`\mathbf{A}_t`
- 希腊字母：`\theta`, `\tau`, `\epsilon`, `\pi`
- 期望：`\mathbb{E}`
- 正态分布：`\mathcal{N}(\mathbf{0}, \mathbf{I})`
- 范数：`\left\| \cdot \right\|^2`
- 上下标：`A_t^{\tau}`, `a_{t+H-1}`
- 矩阵维度：`\mathbb{R}^{w \times d}`

**格式原则**：与原文对齐，不额外添加原文没有的子标题。独立公式单独成段居中，行内公式嵌入文字流中。

## 注意事项

1. **频率限制**：飞书 API 每秒 3 次，文字块可批量提交（多个 children 一次请求），图片必须逐个三步处理，每步间 sleep 0.4s
2. **Token 有效期**：tenant_access_token 有效期 2 小时，长文档操作中途需调用 refresh
3. **图片三步流程**：创建空 Block → 上传素材到 Block → patch 设置 token。绝对不能跳步
4. **权限要求**：应用需开启 `wiki:wiki`、`docx:document`、`drive:drive` 权限
5. **node_type 必传**：创建 wiki 节点时必须传 `"node_type": "origin"`
6. **裁剪必须验证**：每张裁剪的图片都要用 Read 工具目视检查，避免截断或包含无关文字
7. **可复用工具脚本**：`/home/ubuntu/.claude/skills/feishu_paper_tool.py` 包含 `FeishuDocWriter` 类

## 翻译原则

- 保持学术论文的专业术语准确性
- 数学公式使用飞书 equation 元素 + LaTeX 语法，不要用 Unicode 符号凑
- 图表说明翻译后以斜体写入图片下方
- 保留作者姓名原文不翻译
- 章节编号保持原格式（I, II, III...）
- 参考文献编号保留原文引用格式（如 [28, 32]）
- 与原文格式严格对齐：原文没有子标题就不加子标题，原文是连续段落就写连续段落
- 粗体/斜体与原文一致（如术语首次出现时的斜体 *action chunk*、段首粗体标签 **Shirt folding:**）

## Step 10: 逐章 Review 精翻（关键步骤！）

初稿写入飞书后，必须对每一章逐章进行 review 精翻。流程：

**10a. 对照原文逐段检查：**
1. 用 Read 工具重新读取该章对应的 PDF 页面
2. 用飞书 API 获取当前文档中该章的所有 block 内容
3. 逐段对比，检查以下问题：

**10b. 常见问题清单：**
- **信息遗漏**：原文某段有 5 句话，翻译只写了 2 句概括 → 补全所有句子
- **引用缺失**：原文有 [24, 50] 等引用编号，翻译中丢失 → 补回
- **术语不一致**：同一术语在不同段落翻译不同（如 flow matching 有时译"流匹配"有时译"流式匹配"）→ 统一
- **公式遗漏**：原文有行内公式如 $n^{0.43}$，翻译中变成纯文本 → 用 equation 元素
- **格式偏差**：原文的粗体标签（如 **Shirt folding:**）、斜体术语、段落分隔与翻译不一致 → 修正
- **多余标题**：翻译中添加了原文没有的子标题 → 删除
- **图表位置**：图表应出现在原文中首次引用它的段落附近 → 调整位置

**10c. 修正方法：**
- 小范围修改：用 batch_delete 删除有问题的块，在相同 index 插入新块
- 获取当前 block 列表定位：
```python
resp = requests.get(f"{API}/docx/v1/documents/{DOC_ID}/blocks/{DOC_ID}", headers=H)
children = resp.json()["data"]["block"]["children"]
# 找到要修改的章节的 start_index 和 end_index
```
- 替换某章内容：先 batch_delete(start, end)，再在 start 位置 insert 新内容

**10d. Review 顺序：**
按章节顺序逐章 review，每章完成后再进入下一章。不要批量处理多章——每章 review 需要重新读取 PDF 原文对照。

## Step 11: 名词解释子页面（按需）

当用户说"我要名词解释"并给出术语列表时，执行以下流程：

### 11a. 创建名词解释子页面（仅首次）

在主翻译文档的 wiki 节点下创建子页面：
```bash
POST /wiki/v2/spaces/<SPACE_ID>/nodes
Body: {"obj_type":"docx","node_type":"origin","parent_node_token":"<主文档NODE_TOKEN>","title":"名词解释"}
```
记录子页面的 `node_token`（用于构造 URL）和 `obj_token`（用于写入内容）。

页面开头写入引导说明：
```
本页面收录论文中出现的关键术语和技术概念的解释。在主文档中，带下划线的术语可点击跳转到本页对应条目。
```

### 11b. 为每个术语写入解释条目

每个术语作为一个 `heading2` 条目，后跟解释段落。内容应包括：
- 术语的定义和来源（哪篇论文/哪个机构）
- 在本论文中的具体作用
- 关键技术参数（如有）
- 与相关概念的对比（如有）

### 11c. 在主文档中添加跳转链接（关键步骤！）

找到主文档中该术语出现的位置，用 `update_text_elements` 把术语文字改为带链接的版本：

1. 搜索术语在主文档中的 block：
```python
for b in all_blocks:
    for el in b["text"]["elements"]:
        if "text_run" in el and "术语名" in el["text_run"]["content"]:
            # 找到了，记录 block_id 和文字内容
```

2. 拆分文字，让术语变成带链接的 element：
```python
# 原文: "...我们使用 PaliGemma 作为基础模型..."
# 拆为三个 element:
elements = [
    t("...我们使用 "),
    t("PaliGemma", link="https://xxx.feishu.cn/wiki/<名词解释页NODE_TOKEN>"),
    t(" 作为基础模型..."),
]
```

3. 用 PATCH 更新该 block：
```bash
PATCH /docx/v1/documents/<DOC_ID>/blocks/<BLOCK_ID>
Body: {"update_text_elements": {"elements": [...]}}
```

**链接格式**：直接使用原始 URL，不需要 base64 编码：
```json
{"text_run": {"content": "PaliGemma", "text_element_style": {
    "link": {"url": "https://xxx.feishu.cn/wiki/<NODE_TOKEN>"}
}}}
```

**注意**：heading 块不支持 link 属性（会报 schema mismatch），只有 text 块中的 text_run 支持。

### 11d. 术语选取建议

通常需要解释的术语类型：
- 基础模型名称（如 PaliGemma、Gemma、SigLIP）
- 核心方法（如 Flow Matching、Transfusion、Action Chunking）
- 架构组件（如 Action Expert、MQA、Late Fusion）
- 数据集名称（如 OXE、DROID、Bridge v2）
- 评估方法名称（如 ACT、Diffusion Policy、OpenVLA）
