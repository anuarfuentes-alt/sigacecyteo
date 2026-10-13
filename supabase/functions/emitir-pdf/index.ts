import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";
import { PDFDocument, StandardFonts, rgb } from "npm:pdf-lib@1.17.1";
const cors = { "Access-Control-Allow-Origin": Deno.env.get("APP_ORIGIN") ?? "*", "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type", "Access-Control-Allow-Methods": "POST, OPTIONS" };
Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", {headers:cors});
  if (req.method !== "POST") return Response.json({error:"Método no permitido"},{status:405,headers:cors});
  try {
    const authHeader=req.headers.get("Authorization");
    if(!authHeader?.startsWith("Bearer ")) return Response.json({error:"Se requiere iniciar sesión."},{status:401,headers:cors});
    const url=Deno.env.get("SUPABASE_URL"), key=Deno.env.get("SUPABASE_ANON_KEY");
    if(!url||!key) throw new Error("Falta configuración de Supabase.");
    const sb=createClient(url,key,{global:{headers:{Authorization:authHeader}},auth:{persistSession:false,autoRefreshToken:false}});
    const {data:ud,error:ue}=await sb.auth.getUser();
    if(ue||!ud.user) return Response.json({error:"Sesión no válida."},{status:401,headers:cors});
    const {data:p,error:pe}=await sb.from("perfiles").select("rol,activo").eq("id_usuario",ud.user.id).maybeSingle();
    if(pe||!p?.activo||!["Administrador","Operativo"].includes(p.rol)) return Response.json({error:"Sin permisos para emitir documentos."},{status:403,headers:cors});
    const b=await req.json(), types=["Constancia","Citatorio","Memorándum"];
    if(!types.includes(b.tipo_documento)) return Response.json({error:"Tipo de documento inválido."},{status:400,headers:cors});
    const {data:issued,error}=await sb.rpc("emitir_documento",{p_tipo:b.tipo_documento,p_ciclo_fiscal:String(b.ciclo_fiscal??new Date().getFullYear()),p_prefijo:String(b.prefijo??"CECYTEO/P14/DIR"),p_id_alumno:b.id_alumno||null,p_datos:b.datos&&typeof b.datos==="object"?b.datos:{}});
    if(error) return Response.json({error:"No fue posible reservar el folio.",details:error.message},{status:400,headers:cors});
    const rec=Array.isArray(issued)?issued[0]:issued;
    if(!rec?.folio_asignado) throw new Error("No se recibió el folio reservado.");
    const pdf=await PDFDocument.create(), page=pdf.addPage([595.28,841.89]);
    const font=await pdf.embedFont(StandardFonts.Helvetica), bold=await pdf.embedFont(StandardFonts.HelveticaBold), green=rgb(.12,.30,.20);
    page.drawText("CECyTEO",{x:55,y:780,size:21,font:bold,color:green});
    page.drawText("COLEGIO DE ESTUDIOS CIENTÍFICOS Y TECNOLÓGICOS DEL ESTADO DE OAXACA",{x:55,y:758,size:8,font,color:green});
    page.drawLine({start:{x:55,y:744},end:{x:540,y:744},thickness:1.5,color:green});
    page.drawText(String(b.tipo_documento).toLocaleUpperCase("es-MX"),{x:55,y:700,size:15,font:bold,color:green});
    page.drawText("Folio: "+rec.folio_asignado,{x:55,y:674,size:10,font:bold});
    page.drawText("Fecha: "+new Date(rec.fecha_emision).toLocaleDateString("es-MX"),{x:55,y:654,size:10,font});
    const d=b.datos??{}, lines=[["Destinatario",String(d.nombre_alumno??d.destinatario??d.grupo??"No especificado")],["Matrícula",String(d.matricula??"No especificada")],["Semestre / grupo",String(d.semestre_grupo??d.grupo??"Por validar")],["Asunto / motivo",String(d.motivo??d.asunto??"Documento generado desde control escolar.")]];
    let y=605; for(const [label,value] of lines){page.drawText(label+":",{x:55,y,size:10,font:bold});page.drawText(value.length>85?value.slice(0,82)+"...":value,{x:155,y,size:10,font});y-=29;}
    page.drawText("Se expide el presente documento para los fines administrativos correspondientes.",{x:55,y:y-10,size:10,font});
    page.drawLine({start:{x:185,y:270},end:{x:410,y:270},thickness:.7,color:rgb(.5,.5,.5)});
    page.drawText("ATENTAMENTE",{x:240,y:250,size:10,font:bold});page.drawText("Dirección del Plantel",{x:237,y:230,size:10,font});
    page.drawLine({start:{x:55,y:65},end:{x:540,y:65},thickness:.5,color:green});
    page.drawText("Documento electrónico; firmas y autorizaciones oficiales deben validarse.",{x:55,y:48,size:7,font,color:rgb(.4,.4,.4)});
    return new Response(await pdf.save(),{status:200,headers:{...cors,"Content-Type":"application/pdf",'Content-Disposition':'attachment; filename="'+rec.folio_asignado.replaceAll("/","-")+'.pdf"',"X-Document-Folio":rec.folio_asignado,"Cache-Control":"no-store"}});
  } catch(e) { console.error("emitir-pdf",e); return Response.json({error:"Error interno al generar el documento."},{status:500,headers:cors}); }
});
