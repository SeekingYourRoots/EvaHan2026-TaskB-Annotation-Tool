from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
from pathlib import Path
import copy
import shutil

app = FastAPI(title="数据标注工具")

WORKSPACE_DIR = Path(r"C:\zyj_workspace\stu_workspace\workspace")
DATASET_JSON = WORKSPACE_DIR / "demo.json"
UPDATE_JSON = WORKSPACE_DIR / "update.json"  
IMAGES_DIR = WORKSPACE_DIR / "Dataset_B"


app.mount("/Dataset_B", StaticFiles(directory=str(IMAGES_DIR)), name="images")

class Point(BaseModel):
    x: float
    y: float

class Region(BaseModel):
    label: str
    text: str
    points: List[List[float]]

class ImageData(BaseModel):
    image_path: str
    regions: List[Region]

class SaveRequest(BaseModel):
    image_index: int
    new_regions: List[Region]

class ExportRequest(BaseModel):
    filename: str


original_dataset = [] 
current_dataset = []  


def load_dataset():
    global original_dataset, current_dataset
    
    with open(DATASET_JSON, 'r', encoding='utf-8') as f:
        original_dataset = json.load(f)
    
    need_init = False
    if not UPDATE_JSON.exists():
        need_init = True
        print(f"update.json 不存在，将从 Dataset_B.json 初始化")
    else:

        try:
            with open(UPDATE_JSON, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    need_init = True
                    print(f"update.json 为空，将重新初始化")
                else:
                    current_dataset = json.loads(content)
                    print(f"加载完成：原始数据 {len(original_dataset)} 条，当前数据 {len(current_dataset)} 条")
        except json.JSONDecodeError as e:
            need_init = True
            print(f"update.json 格式错误：{e}，将重新初始化")

    if need_init:
        shutil.copy(DATASET_JSON, UPDATE_JSON)
        print(f"初始化 update.json 完成")
        with open(UPDATE_JSON, 'r', encoding='utf-8') as f:
            current_dataset = json.load(f)

load_dataset()

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """返回主页面HTML"""
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/images/count")
async def get_image_count():
    """获取图片总数"""
    return {"count": len(current_dataset)}

@app.get("/api/images/{image_index}")
async def get_image_data(image_index: int):
    """获取指定图片的数据"""
    if image_index < 0 or image_index >= len(current_dataset):
        raise HTTPException(status_code=404, detail="图片不存在")
    
    current_data = current_dataset[image_index]
    original_data = original_dataset[image_index]
    
    original_regions = original_data["regions"]
    current_regions = current_data["regions"]
    
    new_regions = []
    if len(current_regions) > len(original_regions):
        new_regions = current_regions[len(original_regions):]
    
    return {
        "image_path": current_data["image_path"],
        "original_regions": original_regions,
        "new_regions": new_regions,
        "image_index": image_index,
        "total_images": len(current_dataset)
    }

@app.post("/api/save")
async def save_annotation(request: SaveRequest):
    """保存标注数据到 update.json"""
    if request.image_index < 0 or request.image_index >= len(current_dataset):
        raise HTTPException(status_code=404, detail="图片不存在")
    
    original_regions = original_dataset[request.image_index]["regions"]

    current_dataset[request.image_index]["regions"] = original_regions + [r.dict() for r in request.new_regions]
    
    with open(UPDATE_JSON, 'w', encoding='utf-8') as f:
        json.dump(current_dataset, f, ensure_ascii=False, indent=2)
    
    print(f"保存成功：图片 {request.image_index}，新增标注 {len(request.new_regions)} 个")
    
    return {"status": "success", "message": "保存成功"}

@app.delete("/api/regions/{image_index}/{region_index}")
async def delete_region(image_index: int, region_index: int):
    """删除指定的新增区域"""
    if image_index < 0 or image_index >= len(current_dataset):
        raise HTTPException(status_code=404, detail="图片不存在")
    
    original_count = len(original_dataset[image_index]["regions"])
    
    if region_index < original_count:
        raise HTTPException(status_code=403, detail="不能删除原始标注")
    
    del current_dataset[image_index]["regions"][region_index]
    
    with open(UPDATE_JSON, 'w', encoding='utf-8') as f:
        json.dump(current_dataset, f, ensure_ascii=False, indent=2)
    
    return {"status": "success"}

@app.put("/api/regions/{image_index}/{region_index}/label")
async def update_region_label(image_index: int, region_index: int, label: str):
    """修改指定区域的标签类型"""
    if image_index < 0 or image_index >= len(current_dataset):
        raise HTTPException(status_code=404, detail="图片不存在")
    
    if region_index < 0 or region_index >= len(current_dataset[image_index]["regions"]):
        raise HTTPException(status_code=404, detail="区域不存在")
    
    # 验证标签类型
    valid_labels = ['text', 'image', 'seal', 'book_edge']
    if label not in valid_labels:
        raise HTTPException(status_code=400, detail=f"无效的标签类型: {label}")
    
    # 修改标签
    current_dataset[image_index]["regions"][region_index]["label"] = label
    
    # 同时更新原始数据集（如果是原始区域）
    if region_index < len(original_dataset[image_index]["regions"]):
        original_dataset[image_index]["regions"][region_index]["label"] = label
    
    # 保存到 update.json
    with open(UPDATE_JSON, 'w', encoding='utf-8') as f:
        json.dump(current_dataset, f, ensure_ascii=False, indent=2)
    
    print(f"修改成功：图片 {image_index}，区域 {region_index}，新标签 {label}")
    
    return {"status": "success", "message": "标签修改成功", "new_label": label}

@app.post("/api/export")
async def export_dataset(request: ExportRequest):
    """导出当前数据集并清空 update.json"""
    try:
        filename = request.filename
        if not filename.endswith('.json'):
            filename = f"{filename}.json"
        
        export_path = WORKSPACE_DIR / filename
        
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(current_dataset, f, ensure_ascii=False, indent=2)
        
        print(f"导出成功：{export_path}")
        
        with open(UPDATE_JSON, 'w', encoding='utf-8') as f:
            f.write('')
        
        print(f"update.json 已清空")
        print("服务器将在 2 秒后关闭...")
        
        import asyncio
        asyncio.create_task(shutdown_server())
        
        return {"status": "success", "message": f"数据已保存为 {filename}，update.json 已清空，服务器即将关闭"}
    
    except Exception as e:
        print(f"导出失败：{e}")
        raise HTTPException(status_code=500, detail=f"导出失败：{str(e)}")

async def shutdown_server():
    """延迟关闭服务器"""
    import asyncio
    await asyncio.sleep(2)
    print("正在关闭服务器...")
    os._exit(0)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7896)