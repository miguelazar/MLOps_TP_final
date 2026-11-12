const fs=require('fs');
const {instance}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1110-973-0_26.1110.973.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/@viz-js/viz');
const rows=[
['1.1',5,'Revisar alcance',''],['1.2',15,'Arquitectura','1.1'],['1.3',12,'Escenarios y métricas','1.1'],
['2.1',6,'Fuentes y licencias','1.1'],['2.2',22,'Explorar datos','2.1'],['2.3',26,'Anotar secuencias','2.2 1.3 4.1'],['2.4',12,'Particionar datos','2.3'],['2.5',14,'Variantes normales','2.4'],
['3.1',10,'Reproducir video','1.2'],['3.2',20,'Adaptar detector','1.2 2.2'],['3.3',20,'Seguimiento','3.1 3.2'],['3.4',15,'Evaluar seguimiento','3.3 2.4'],
['4.1',18,'Definir normalidad','1.3 2.2'],['4.2',24,'Entrenar base','4.1 2.5 3.3'],['4.3',28,'Ajustar modelo','4.2 3.4'],['4.4',20,'Evaluar eventos','4.3'],
['5.1',10,'Telemetría simulada','1.2'],['5.2',20,'Posición e incertidumbre','5.1'],['5.3',10,'Administrar recursos','1.2'],['5.4',15,'Recomendar recursos','5.2 5.3'],['5.5',10,'Evaluar localización','5.4 1.3'],
['6.1',15,'Comunicar con dron','1.2'],['6.2',15,'Reobservación','6.1 3.1 4.4'],['6.3',18,'Asistencia simulada','6.1 4.4 5.4'],['6.4',12,'Verificar simulación','6.2 6.3 1.3'],
['7.1',20,'Interfaz del operador','1.2'],['7.2',12,'Corrección y etiquetas','7.1'],['7.3',14,'Seleccionar ejemplos','7.2 4.1'],['7.4',14,'Actualizar modelo','7.3 4.4'],
['8.1',20,'Integrar componentes','3.4 5.5 6.4 7.4'],['8.2',15,'Pruebas funcionales','8.1'],['8.3',18,'Evaluación final','8.2'],['8.4',12,'Corregir y verificar','8.3'],
['9.1',18,'Documentación y manual','8.4'],['9.2',32,'Redactar memoria','8.4'],['9.3',13,'Revisar memoria','9.2'],['9.4',12,'Defensa y entregables','9.1 9.3']];
const nodes=Object.fromEntries(rows.map(([id,d,label,p])=>[id,{id,d,label,p:p?p.split(' '):[],es:0,ef:0}]));
const done=new Set();
while(done.size<rows.length){let progress=false;for(const n of Object.values(nodes)){if(done.has(n.id)||!n.p.every(p=>done.has(p)))continue;n.es=Math.max(0,...n.p.map(p=>nodes[p].ef));n.ef=n.es+n.d;done.add(n.id);progress=true;}if(!progress)throw Error('Cycle');}
const duration=Math.max(...Object.values(nodes).map(n=>n.ef));
for(const id of [...done].reverse()){const n=nodes[id];const children=Object.values(nodes).filter(x=>x.p.includes(id));n.lf=children.length?Math.min(...children.map(x=>x.ls)):duration;n.ls=n.lf-n.d;n.critical=n.ls===n.es;}
const critical=Object.values(nodes).filter(n=>n.critical).map(n=>n.id);
const nid=id=>'n'+id.replace('.','_');
let dot='digraph AON { graph [rankdir=TB, ranksep=0.18, nodesep=0.13, splines=ortho, bgcolor="transparent"]; node [shape=box, style="rounded,filled", fontname="Arial", fontsize=11, margin="0.06,0.04", fillcolor="#DFEDF5", color="#8896A0", penwidth=0.6]; edge [color="#A5ADB3", arrowsize=0.5, penwidth=0.65];\n';
dot+='start [label="Inicio",shape=ellipse]; finish [label="Fin",shape=ellipse];\n';
for(const n of Object.values(nodes))dot+=`${nid(n.id)} [label=${JSON.stringify('Tarea '+n.id+' · '+n.d+' h\n'+n.label)},fillcolor="${n.critical?'#F7D9C4':'#DFEDF5'}"];\n`;
for(const n of Object.values(nodes)){for(const p of n.p){const crit=n.critical&&nodes[p].critical&&nodes[p].ef===n.es;dot+=`${nid(p)} -> ${nid(n.id)} [color="${crit?'#B46F46':'#A5ADB3'}",penwidth=${crit?1.5:0.65}];\n`;}}
dot+='start -> n1_1 [color="#B46F46",penwidth=1.5]; n9_4 -> finish [color="#B46F46",penwidth=1.5]; }';
(async()=>{const viz=await instance();fs.writeFileSync(__dirname+'/aon.dot',dot);fs.writeFileSync(__dirname+'/aon.svg',viz.renderString(dot,{format:'svg'}));fs.writeFileSync(__dirname+'/layout.json',viz.renderString(dot,{format:'json'}));fs.writeFileSync(__dirname+'/calculo.json',JSON.stringify({duration,critical,effort:rows.reduce((s,r)=>s+r[1],8),nodes},null,2));console.log(JSON.stringify({duration,critical,effort:rows.reduce((s,r)=>s+r[1],8)}));})();
