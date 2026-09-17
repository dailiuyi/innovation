"""Generate the V0.1 database relationship diagram as SVG and PNG (requires Pillow)."""
from pathlib import Path
from html import escape
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
OUT.mkdir(exist_ok=True)
W, H = 1280, 1110
SCALE = 2
im = Image.new("RGB", (W*SCALE, H*SCALE), "#f8fafc")
d = ImageDraw.Draw(im)
font_path = Path("C:/Windows/Fonts/msyh.ttc")
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
       '<title id="title">乌托邦世界 V0.1 数据库关系</title>',
       '<desc id="desc">保留场景、内容版本、成品文件的分离；文件关联粒度待交付格式确认。</desc>',
       f'<rect width="{W}" height="{H}" fill="#f8fafc"/>']

def box(x,y,w,h,fill="#ffffff",stroke="#cbd5e1",radius=12):
    d.rounded_rectangle((x*SCALE,y*SCALE,(x+w)*SCALE,(y+h)*SCALE),radius*SCALE,fill,stroke,2)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>')

def text(x,y,value,size=20,color="#172b4d"):
    font=ImageFont.truetype(str(font_path),size*SCALE)
    d.text((x*SCALE,y*SCALE),value,font=font,fill=color,anchor="lt")
    svg.append(f'<text x="{x}" y="{y}" dominant-baseline="text-before-edge" font-family="Microsoft YaHei, Noto Sans CJK SC, sans-serif" font-size="{size}" fill="{color}">{escape(value)}</text>')

def arrow(x1,y1,x2,y2,color="#2563eb"):
    d.line((x1*SCALE,y1*SCALE,x2*SCALE,y2*SCALE),fill=color,width=3*SCALE)
    if x1==x2:
        sign=1 if y2>y1 else -1
        points=[(x2,y2),(x2-6,y2-sign*10),(x2+6,y2-sign*10)]
    else:
        sign=1 if x2>x1 else -1
        points=[(x2,y2),(x2-sign*10,y2-6),(x2-sign*10,y2+6)]
    d.polygon([(x*SCALE,y*SCALE) for x,y in points],fill=color)
    svg.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="3"/>')
    svg.append('<polygon points="'+ ' '.join(f'{x},{y}' for x,y in points)+f'" fill="{color}"/>')


def card(x,y,title,cn,lines,w=230,h=164,fill="#ffffff"):
    box(x,y,w,h,fill)
    text(x+16,y+14,title,23)
    text(x+16,y+50,cn,19,"#2563eb")
    for i,line in enumerate(lines):
        text(x+16,y+86+i*26,line,16)

text(40,26,"V0.1 数据模型 · 已确定边界与待确认方案",32)
text(40,78,"蓝色：已确定关系；橙色：待确认。此图表达设计边界，不是最终物理表结构。",19,"#52647c")
text(40,127,"01  保留三层分离",24)
card(40,176,"scene","场景",["在哪里展示","位置、入口、固定坐标"],w=300)
card(460,176,"scene_version","内容版本",["这次发布什么内容","昼夜类型、版本号、播放配置"],w=300)
card(880,176,"asset","成品文件",["实际交付物是什么","对象键、大小、摘要、验证状态"],w=335)
arrow(340,259,460,259)
text(352,225,"1 → 0..N",17)
arrow(760,259,880,259,"#b45309")
text(772,225,"关联待定",17,"#b45309")
arrow(155,340,155,427)
text(172,363,"1 → 0..N",17,"#2563eb")
card(40,427,"marker","场景标记",["主键 id / 外键 scene_id","入口码、尺寸、位置与朝向"],h=157)
box(355,379,860,205,"#fff7ed","#e9b276")
text(377,397,"先确认成品格式，再决定文件粒度",22,"#b45309")
text(377,438,"完整包：按平台登记成品包，包内资源交给制作工具管理。",19)
text(377,476,"入口与依赖集合：确认客户端需求后，再设计文件关联及依赖检查。",19)
text(377,518,"现有 version_asset 仅为候选；暂不确定文件数量、复用与关联表形式。",18)
text(40,622,"02  当前发布版本 · 同一组场景与版本表",24)
box(40,668,1175,130,"#ecfdf5","#6bbba5")
text(62,687,"scene.current_day_version_id     →  白天内容版本（0 或 1 个）",21,"#087f6f")
text(62,724,"scene.current_night_version_id  →  夜晚内容版本（0 或 1 个）",21,"#087f6f")
text(62,764,"此处箭头表示指针方向。两项均引用同场景的 scene_version；为空表示对应入口下线。",17)
text(40,837,"03  账号与审计 · 下方版本、文件名称复用上方的表",24)
card(40,892,"admin_user","管理员账号",["主键 id / 独立账号","全部管理员权限相同"],w=265,h=163)
for y,target in [(909,"scene_version.created_by → 版本创建人"),(962,"asset.created_by → 文件登记人"),(1015,"audit_log.actor_id → 操作记录所属账号")]:
    arrow(305,y+12,470,y+12)
    box(335,y-4,100,31,"#f8fafc","#f8fafc",0)
    text(345,y,"1 → 0..N",17,"#2563eb")
    box(470,y-5,745,43,"#ffffff")
    text(489,y+4,target,20)
text(40,1073,"audit_log 保存动作、对象 ID、详情和时间；object_id 是业务引用，未声明为业务表外键。",18,"#52647c")
svg.append('</svg>')
(OUT/'database-v0.1.svg').write_text('\n'.join(svg),encoding='utf-8')
im.save(OUT/'database-v0.1.png')
print('Generated database relationship SVG and PNG')
