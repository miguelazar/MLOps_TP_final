import json, os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pypdfium2 as pdfium
from pypdf import PdfReader
base=os.path.dirname(__file__)
g=json.load(open(os.path.join(base,'layout.json'),encoding='utf-8'))
calc=json.load(open(os.path.join(base,'calculo.json'),encoding='utf-8'))
pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialBold','C:/Windows/Fonts/arialbd.ttf'))
W,H=A4
out=os.path.join(base,'aon-a4.pdf')
c=canvas.Canvas(out,pagesize=A4)
c.setTitle('Red AON - Camino crítico')
c.setFillColor(HexColor('#263642'));c.setFont('Arial',16)
c.drawString(24,H-30,'Red AON · Trabajo Final')
c.setFont('Arial',8);c.drawString(24,H-45,'Dependencias propuestas | Esfuerzo total: 600 h | Recursos paralelos sin restricciones')
for x,color,text in [(24,'#F7D9C4','Camino crítico'),(160,'#DFEDF5','Otras actividades')]:
 c.setFillColor(HexColor(color));c.roundRect(x,H-65,12,9,2,fill=1,stroke=0)
 c.setFillColor(HexColor('#263642'));c.drawString(x+17,H-64,text)
x0,y0,x1,y1=map(float,g['bb'].split(','))
s=min((W-48)/(x1-x0),(H-150)/(y1-y0))
ox=(W-(x1-x0)*s)/2;oy=78+(H-150-(y1-y0)*s)/2
c.saveState();c.translate(ox,oy);c.scale(s,s)
def draw_ops(ops):
 for op in ops:
  typ=op['op']
  if typ in ('c','C'):
   color=op['color'];col=HexColor(color[:7]) if color.startswith('#') else HexColor('#A5ADB3')
   (c.setStrokeColor if typ=='c' else c.setFillColor)(col)
  elif typ=='S':
   st=op['style']
   if st.startswith('setlinewidth('):c.setLineWidth(float(st[13:-1]))
  elif typ in ('b','B'):
   pts=op['points'];p=c.beginPath();p.moveTo(*pts[0])
   for i in range(1,len(pts),3):p.curveTo(*(pts[i]+pts[i+1]+pts[i+2]))
   c.drawPath(p,stroke=1,fill=typ=='B')
  elif typ in ('P','p','L'):
   pts=op['points'];p=c.beginPath();p.moveTo(*pts[0])
   for pt in pts[1:]:p.lineTo(*pt)
   if typ!='L':p.close()
   c.drawPath(p,stroke=1,fill=typ=='P')
for edge in g.get('edges',[]):
 c.setLineWidth(.65);draw_ops(edge.get('_draw_',[]));draw_ops(edge.get('_hdraw_',[]))
for n in g['objects']:
 x,y=map(float,n['pos'].split(','));w=float(n['width'])*72;h=float(n['height'])*72
 c.setFillColor(HexColor(n.get('fillcolor','#DFEDF5')));c.setStrokeColor(HexColor('#8896A0'));c.setLineWidth(.6)
 c.roundRect(x-w/2,y-h/2,w,h,4,fill=1,stroke=1)
 c.setFillColor(HexColor('#263642'));lines=n['label'].replace(chr(92)+'n',chr(10)).splitlines();size=11
 for i,line in enumerate(lines):
  c.setFont('Arial',size)
  c.drawCentredString(x,y+(len(lines)-1)*6-i*12-3.5,line)
c.restoreState()
c.setFillColor(HexColor('#263642'));c.setFont('Arial',8)
c.drawString(24,60,'Duración teórica de la red: '+str(calc['duration'])+' h (sin restricciones de recursos).')
c.setFont('Arial',7.5)
c.drawString(24,46,'1.4 Planificación y seguimiento: 8 h transversales, incluidas en las 600 h de esfuerzo.')
c.drawString(24,34,'Cada nodo muestra: código de tarea, esfuerzo y nombre abreviado. Flechas: fin a inicio.')
c.save()
reader=PdfReader(out);assert len(reader.pages)==1
page=reader.pages[0];assert abs(float(page.mediabox.width)-W)<1
doc=pdfium.PdfDocument(out);doc[0].render(scale=1.6).to_pil().save(os.path.join(base,'preview.png'))
print(json.dumps({'pages':len(reader.pages),'size_pt':[W,H],'scale':s,'min_font_pt':11*s,'duration':calc['duration']}))
