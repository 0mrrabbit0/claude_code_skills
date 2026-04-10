#!/usr/bin/env python3
"""
Feishu Wiki Paper Tool - 将 PDF 论文翻译为中文并写入飞书知识库

用法:
    python3 feishu_paper_tool.py --app_id <APP_ID> --app_secret <APP_SECRET> \
        --parent_node <PARENT_NODE_TOKEN> --space_id <SPACE_ID> \
        --pdf <PDF_PATH> --title <DOCUMENT_TITLE> \
        [--figures <FIG_DEFINITIONS_JSON>]

此脚本处理:
    1. 获取飞书 tenant_access_token
    2. 在知识库中创建文档节点
    3. 从 PDF 中提取/渲染图片
    4. 通过三步流程插入图片（创建空 Block → 上传素材 → 更新 Block）
    5. 写入文本 Block（标题、段落等）
"""
import requests
import json
import time
import os
import argparse
import sys

class FeishuDocWriter:
    """飞书文档写入器"""

    API_BASE = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self.token = None
        self.doc_id = None
        self.headers = {}
        self.refresh_token()

    def refresh_token(self):
        """获取/刷新 tenant_access_token"""
        resp = requests.post(
            f"{self.API_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret}
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get token: {data}")
        self.token = data["tenant_access_token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        print(f"[Token] Refreshed: {self.token[:20]}...")

    def get_node_info(self, node_token):
        """获取知识库节点信息"""
        url = f"{self.API_BASE}/wiki/v2/spaces/get_node?token={node_token}"
        resp = requests.get(url, headers=self.headers)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get node info: {data}")
        return data["data"]["node"]

    def create_wiki_node(self, space_id, parent_node_token, title):
        """在知识库中创建新文档节点"""
        url = f"{self.API_BASE}/wiki/v2/spaces/{space_id}/nodes"
        resp = requests.post(url, headers=self.headers, json={
            "obj_type": "docx",
            "node_type": "origin",
            "parent_node_token": parent_node_token,
            "title": title
        })
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to create wiki node: {data}")
        node = data["data"]["node"]
        self.doc_id = node["obj_token"]
        print(f"[Wiki] Created node: {node['node_token']}")
        print(f"[Wiki] Document ID: {self.doc_id}")
        print(f"[Wiki] URL: https://huazhi-ai.feishu.cn/wiki/{node['node_token']}")
        return node

    def add_blocks(self, parent_id, blocks):
        """向父 Block 添加子 Block"""
        url = f"{self.API_BASE}/docx/v1/documents/{self.doc_id}/blocks/{parent_id}/children"
        resp = requests.post(url, headers=self.headers, json={"children": blocks})
        data = resp.json()
        if data.get("code") != 0:
            print(f"  [ERROR] add_blocks: {data.get('code')} - {data.get('msg')}")
            return None
        return data

    def insert_image(self, parent_id, image_path):
        """
        三步插入图片:
        1. 创建空 Image Block
        2. 以 Image BlockID 为 parent_node 上传图片素材
        3. 调用 patch 接口设置图片 token
        """
        filename = os.path.basename(image_path)
        print(f"  [Image] Inserting: {filename}")

        # Step 1: 创建空图片 Block
        result = self.add_blocks(parent_id, [{"block_type": 27, "image": {}}])
        if not result or not result.get("data", {}).get("children"):
            print(f"    [FAIL] Cannot create image block")
            return False
        block_id = result["data"]["children"][0]["block_id"]
        print(f"    Block: {block_id}")
        time.sleep(0.4)

        # Step 2: 上传图片素材
        file_size = os.path.getsize(image_path)
        upload_headers = {"Authorization": f"Bearer {self.token}"}
        with open(image_path, "rb") as f:
            resp = requests.post(
                f"{self.API_BASE}/drive/v1/medias/upload_all",
                headers=upload_headers,
                data={
                    "file_name": filename,
                    "parent_type": "docx_image",
                    "parent_node": block_id,
                    "size": str(file_size)
                },
                files={"file": (filename, f, "image/png")}
            )
        data = resp.json()
        if data.get("code") != 0:
            print(f"    [FAIL] Upload: {data}")
            return False
        file_token = data["data"]["file_token"]
        print(f"    Token: {file_token}")
        time.sleep(0.4)

        # Step 3: 更新 Block 设置素材
        patch_url = f"{self.API_BASE}/docx/v1/documents/{self.doc_id}/blocks/{block_id}"
        resp = requests.patch(patch_url, headers=self.headers,
                             json={"replace_image": {"token": file_token}})
        data = resp.json()
        if data.get("code") != 0:
            print(f"    [FAIL] Patch: {data}")
            return False
        print(f"    [OK] Image inserted!")
        return True

    # ========== Block 构建辅助方法 ==========

    @staticmethod
    def text_element(content, bold=False, italic=False):
        return {
            "text_run": {
                "content": content,
                "text_element_style": {
                    "bold": bold, "italic": italic,
                    "strikethrough": False, "underline": False, "inline_code": False
                }
            }
        }

    @classmethod
    def text_block(cls, text, bold=False, italic=False):
        return {
            "block_type": 2,
            "text": {
                "elements": [cls.text_element(text, bold, italic)],
                "style": {}
            }
        }

    @staticmethod
    def heading_block(text, level=1):
        """level: 1-9 对应 heading1-heading9, block_type = level + 2"""
        key = f"heading{level}"
        return {
            "block_type": level + 2,
            key: {
                "elements": [FeishuDocWriter.text_element(text, bold=True)],
                "style": {}
            }
        }

    @staticmethod
    def divider_block():
        return {"block_type": 22, "divider": {}}

    # ========== 便捷方法 ==========

    def write_text(self, text, bold=False, italic=False):
        """写入一段文本"""
        return self.add_blocks(self.doc_id, [self.text_block(text, bold, italic)])

    def write_heading(self, text, level=1):
        """写入标题"""
        return self.add_blocks(self.doc_id, [self.heading_block(text, level)])

    def write_divider(self):
        """写入分割线"""
        return self.add_blocks(self.doc_id, [self.divider_block()])

    def write_image(self, image_path):
        """写入图片"""
        return self.insert_image(self.doc_id, image_path)

    def write_batch(self, blocks):
        """批量写入多个 Block"""
        return self.add_blocks(self.doc_id, blocks)


def extract_pdf_figures(pdf_path, output_dir):
    """从 PDF 渲染每一页为高分辨率图片"""
    import fitz  # PyMuPDF
    os.makedirs(output_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        mat = fitz.Matrix(2, 2)  # 2x 分辨率
        pix = page.get_pixmap(matrix=mat)
        img_path = os.path.join(output_dir, f"page_{page_num + 1}.png")
        pix.save(img_path)
        pages.append(img_path)
        print(f"[PDF] Rendered page {page_num + 1}: {os.path.getsize(img_path)} bytes")

    print(f"[PDF] Total pages: {len(pages)}")
    return pages


def crop_figure(page_image_path, crop_box, output_path):
    """
    从页面图片中裁剪指定区域
    crop_box: (left, top, right, bottom)
    """
    from PIL import Image
    img = Image.open(page_image_path)
    cropped = img.crop(crop_box)
    cropped.save(output_path)
    print(f"[Crop] {output_path}: {cropped.size}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Feishu Wiki Paper Tool")
    parser.add_argument("--app_id", required=True, help="飞书应用 App ID")
    parser.add_argument("--app_secret", required=True, help="飞书应用 App Secret")
    parser.add_argument("--parent_node", required=True, help="父节点 token")
    parser.add_argument("--space_id", help="知识库空间 ID (可自动获取)")
    parser.add_argument("--pdf", required=True, help="PDF 文件路径")
    parser.add_argument("--title", required=True, help="文档标题")
    parser.add_argument("--render_pages", action="store_true", help="渲染 PDF 页面为图片")

    args = parser.parse_args()

    # 初始化
    writer = FeishuDocWriter(args.app_id, args.app_secret)

    # 获取 space_id
    space_id = args.space_id
    if not space_id:
        node_info = writer.get_node_info(args.parent_node)
        space_id = node_info["space_id"]
        print(f"[Wiki] Auto-detected space_id: {space_id}")

    # 创建文档
    node = writer.create_wiki_node(space_id, args.parent_node, args.title)

    # 渲染 PDF
    if args.render_pages:
        fig_dir = os.path.join(os.path.dirname(args.pdf), "figures")
        pages = extract_pdf_figures(args.pdf, fig_dir)
        print(f"\nPages rendered to: {fig_dir}")
        print("Use FeishuDocWriter API to add content and images programmatically.")

    print(f"\nDocument created! doc_id={writer.doc_id}")
    print("Use the FeishuDocWriter class to add translated content.")
