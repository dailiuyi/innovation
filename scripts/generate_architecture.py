"""Generate the V0.1 architecture overview as SVG and PNG (requires Pillow)."""
from pathlib import Path
from html import escape
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
OUT.mkdir(exist_ok=True)
W, H = 1120, 1120
SCALE = 2
im = Image.new("RGB", (W*SCALE, H*SCALE), "#f8fafc")
d = ImageDraw.Draw(im)
font_path = Path("C:/Windows/Fonts/msyh.ttc")
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
       '<title id="title">乌托邦世界 V0.1 系统结构</title>',
       '<desc id="desc">客户端访问单个 Spring Boot 应用，应用管理 PostgreSQL 元数据和对象存储文件。管理页面直传文件，用户端直接下载文件。所有组件尚未部署。</desc>',
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

text(40,28,"乌托邦世界 · V0.1 系统结构",32)
text(40,78,"设计阶段 · 尚未部署",18,"#52647c")
box(40,122,1040,64,"#f1f5f9")
text(60,138,"平台外：人工扫描 → GS 重建 → 编辑与构建 → 形成资源包",21)
text(40,215,"01  客户端",18,"#52647c")
box(120,252,390,104,"#eff6ff","#93b4ef")
text(144,269,"内部管理页面",24)
text(144,312,"登录 · 管理场景 · 预览与发布",18)
box(610,252,390,104,"#eff6ff","#93b4ef")
text(634,269,"用户端 APP / 小程序",24)
text(634,312,"识别标记 · 下载与播放 · 恢复定位",18)
arrow(315,356,315,435)
text(125,380,"管理请求 / 上传凭证",18,"#2563eb")
arrow(805,356,805,435)
text(815,380,"扫码请求 / 运行清单",18,"#2563eb")
box(120,435,880,196,"#eef2ff","#879be4")
text(144,453,"02  Spring Boot 后端",26)
text(144,494,"一个应用、一个实例；下列模块在同一进程中运行",18)
for x,title,sub in [(144,"auth","账号与登录"),(354,"scene","场景与标记"),(564,"asset","文件登记与校验"),(774,"version","版本与发布")]:
    box(x,539,194,68,"#ffffff","#c3cdef",8)
    text(x+14,545,title,20)
    text(x+14,577,sub,16)
arrow(315,631,315,714)
box(140,650,355,40,"#f8fafc","#f8fafc",0)
text(148,659,"业务数据读写 / 发布事务",18,"#2563eb")
arrow(805,631,805,714)
box(630,650,350,40,"#f8fafc","#f8fafc",0)
text(640,659,"文件读取校验 / 固定最终对象",18,"#2563eb")
box(120,714,390,133,"#ffffff","#a5b4c8")
text(144,729,"03  PostgreSQL",25)
text(144,774,"7 张表：账号、场景、版本、文件元数据",16)
text(144,805,"版本文件关联、标记、审计",16)
box(610,714,390,133,"#ecfdf5","#6bbba5")
text(634,729,"03  对象存储 · 私有桶",25)
text(634,774,"保存资源文件：上传区 → 最终文件区",16)
text(634,805,"使用凭证访问，最终文件不可覆盖",16)
text(40,878,"文件直传与下载",23)
text(40,916,"以下复用上方组件：客户端获得后端授权后，直接访问对象存储。",17,"#52647c")
for y,left,label,right in [(957,"管理页面","凭上传凭证直传成品","对象存储"),(1028,"对象存储","凭签名链接下载文件","用户端")]:
    box(120,y,190,49,"#ecfdf5","#6bbba5",8)
    text(147,y+10,left,19)
    arrow(327,y+25,787,y+25,"#087f6f")
    box(420,y+2,280,39,"#f8fafc","#f8fafc",0)
    text(433,y+9,label,19,"#087f6f")
    box(805,y,195,49,"#ecfdf5","#6bbba5",8)
    text(837,y+10,right,19)
svg.append('</svg>')
(OUT/'architecture-v0.1.svg').write_text('\n'.join(svg),encoding='utf-8')
im.save(OUT/'architecture-v0.1.png')
print('Generated architecture SVG and PNG')
