#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 resolution;
    float clock;
    float energy;
    float phase;
};
const float PI = 3.14159265359;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
float noise(vec2 p) {
    vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
    return mix(mix(hash(i), hash(i+vec2(1,0)), f.x),
               mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);
}
float fbm(vec2 p) { return .57*noise(p)+.28*noise(p*2.03+4.7)+.15*noise(p*4.11-3.1); }
mat2 rot(float a) { return mat2(cos(a),-sin(a),sin(a),cos(a)); }
void main() {
    vec2 p=(qt_TexCoord0-.5)*2.0;
    float t=clock*(phase>1.5 && phase<2.5 ? 1.45 : 1.0);
    float e=clamp(energy,0.0,1.0);
    vec2 q=rot(.16*t)*p;
    float rr=length(q), a=atan(q.y,q.x);
    float field=fbm(q*3.2+vec2(.23*t,-.19*t));
    float warp=sin(a*3.0+t*.72)*.032+sin(a*7.0-t*.45)*.016;
    float r=rr/(.93+e*.10)+warp+(field-.5)*(.07+e*.10);
    float sphere=1.0-smoothstep(.61,.74,r);
    float z=sqrt(max(0.0,1.0-pow(r/.73,2.0)));
    float angular=a+field*1.6+t*.24;
    float w1=sin(angular*18.0+z*14.0-t*1.1+sin(r*23.0-t)*1.5);
    float w2=sin(angular*11.0-z*22.0+t*.75+field*8.0);
    float w3=sin(r*66.0+a*5.0-t*1.8+field*12.0);
    float fiber=pow(max(0.0,1.0-abs(w1)),14.0);
    fiber+=.56*pow(max(0.0,1.0-abs(w2)),18.0);
    fiber+=.28*pow(max(0.0,1.0-abs(w3)),24.0);
    float membrane=exp(-abs(r-.68)*140.0);
    float folds=pow(.5+.5*sin(a*5.0+t*.6+field*5.0),3.0);
    vec3 ice=vec3(.40,.94,1.0), teal=vec3(.025,.43,.49), gold=vec3(1.0,.55,.20);
    if(phase>3.5) { ice=vec3(1.0,.63,.30); teal=vec3(.60,.18,.08); }
    if(phase>4.5) { ice=vec3(1.0,.35,.34); teal=vec3(.56,.06,.12); }
    vec3 col=teal*(.06+z*.18)*sphere;
    col+=mix(ice,teal,clamp(r,0.0,1.0)) * fiber*sphere*(.65+e*.75);
    col+=ice*membrane*(.55+folds*.65);
    float nucleus=length(p-vec2(sin(t*.83)*.07,cos(t*.57)*.06));
    float heart=exp(-nucleus*nucleus*65.0);
    col+=mix(ice,gold,.65+.2*sin(t*.3))*heart*(.38+e*.85);
    float haze=exp(-rr*rr*4.5);
    col+=teal*haze*.18;
    // Dos corrientes elípticas fuera de la membrana, con profundidad variable.
    for(int j=0;j<2;j++) {
        vec2 v=rot(.6+float(j)*1.2+sin(t*.13)*.2)*p;
        float orbit=length(v*vec2(1.0,1.7));
        float line=exp(-abs(orbit-(.78+float(j)*.045))*170.0);
        col+=ice*line*(.08+.15*max(0.0,v.y));
    }
    // Partículas ligadas al campo, no una lluvia aleatoria sobre el escritorio.
    float dots=0.0;
    for(int i=0;i<12;i++) {
        float k=float(i), th=k*2.39996+t*(.18+mod(k,3.0)*.035);
        vec2 pos=rot(.6)*vec2(cos(th)*(.76+sin(k)*.06),sin(th)*.47);
        float d=length(p-pos);
        dots+=exp(-d*d*(5000.0-2500.0*e))*(.25+.3*sin(k+t)*sin(k+t));
    }
    col+=ice*dots;
    float alpha=clamp(sphere*.80+haze*.20+membrane*.5+dots*.5,0.0,1.0);
    alpha*=1.0-smoothstep(.89,.99,rr);
    col=1.0-exp(-col*1.65);
    fragColor=vec4(col*alpha,alpha)*qt_Opacity;
}
