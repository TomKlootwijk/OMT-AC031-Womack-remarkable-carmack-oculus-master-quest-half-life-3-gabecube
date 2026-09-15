// TOMAGI 1.0 WebGPU kernel: one canonical transition per invocation.
struct State64 { q: vec4<u32>, v: vec4<u32>, topo: vec4<u32>, outv: vec4<u32> };
struct Cell48 { head: vec4<u32>, args: vec4<u32>, tail: vec4<u32> };
struct Params { state_count: u32, cell_count: u32, seed: u32, reserved: u32 };
struct WideI32 { hi: i32, lo: u32 };

@group(0) @binding(0) var<storage, read_write> states: array<State64>;
@group(0) @binding(1) var<storage, read> cells: array<Cell48>;
@group(0) @binding(2) var<uniform> params: Params;

const RHO_N:u32=1u<<20u; const THETA_N:u32=1u<<18u; const TIME_N:u32=1u<<14u; const PHI_N:u32=1u<<12u;
const STATUS_HALT:u32=1u; const STATUS_ZERO:u32=2u; const STATUS_WRAP:u32=4u; const STATUS_EMIT:u32=8u;
const STATUS_CONE:u32=16u; const STATUS_SPHERE:u32=32u; const STATUS_REKEY_MISS:u32=64u; const STATUS_PHI_WRAP:u32=128u;
const FLAG_REKEY:u32=1u<<31u;

fn mix32(x0:u32)->u32 { var x=x0; x^=x>>16u; x*=0x7feb352du; x^=x>>15u; x*=0x846ca68bu; x^=x>>16u; return x; }
fn rotl32(x:u32,r0:u32)->u32 { let r=r0&31u; return (x<<r)|(x>>((32u-r)&31u)); }
fn normi(x:i32,n:i32)->i32 { let r=x%n; return select(r,r+n,r<0); }
fn floordiv(x:i32,n:i32)->i32 { let q=x/n; let r=x%n; return select(q,q-1,r<0); }
fn cycdelta(x:i32,c:i32,n:i32)->i32 { let d=normi(x-c,n); return select(d,d-n,d>=n/2); }
fn addDivmod(a:i32,b:i32,n:i32)->vec2<i32> {
  let qa=floordiv(a,n); let qb=floordiv(b,n);
  let ra=a-qa*n; let rb=b-qb*n; let sum=ra+rb; let carry=sum/n;
  return vec2<i32>(qa+qb+carry,sum-carry*n);
}
fn wideFromI32(value:i32)->WideI32 { return WideI32(select(0,-1,value<0),bitcast<u32>(value)); }
fn wideSub(a:WideI32,b:WideI32)->WideI32 {
  let borrow=select(0,1,a.lo<b.lo);
  return WideI32(a.hi-b.hi-borrow,a.lo-b.lo);
}
fn wideSubI32(a:i32,b:i32)->WideI32 { return wideSub(wideFromI32(a),wideFromI32(b)); }
fn wideNeg(value:WideI32)->WideI32 {
  let borrow=select(0,1,value.lo!=0u);
  return WideI32(0-value.hi-borrow,0u-value.lo);
}
fn wideAbs(value:WideI32)->WideI32 { if(value.hi<0){return wideNeg(value);} return value; }
fn wideAbsI32(value:i32)->WideI32 { return wideAbs(wideFromI32(value)); }
fn wideLess(a:WideI32,b:WideI32)->bool { return a.hi<b.hi || (a.hi==b.hi && a.lo<b.lo); }
fn wideMax(a:WideI32,b:WideI32)->WideI32 { if(wideLess(a,b)){return b;} return a; }

fn packKey(s:State64)->vec2<u32> {
  let rho=u32(normi(bitcast<i32>(s.q.x),i32(RHO_N))); let th=u32(normi(bitcast<i32>(s.q.y),i32(THETA_N)));
  let ti=u32(normi(bitcast<i32>(s.q.z),i32(TIME_N))); let ph=u32(normi(bitcast<i32>(s.q.w),i32(PHI_N)));
  return vec2<u32>((rho<<12u)|(th>>6u),((th&63u)<<26u)|(ti<<12u)|ph);
}
fn normalized(s0:State64)->State64 { var s=s0; s.q.y=u32(normi(bitcast<i32>(s.q.y),i32(THETA_N))); s.q.z=u32(normi(bitcast<i32>(s.q.z),i32(TIME_N))); s.q.w=u32(normi(bitcast<i32>(s.q.w),i32(PHI_N))); s.topo.x&=1u; s.topo.z&=1u; return s; }
fn setField(s0:State64,idx:u32,val:i32,add:bool)->State64 {
  var s=s0; let u=bitcast<u32>(val);
  if(idx==0u){s.q.x=select(u,s.q.x+u,add);} else if(idx==1u){s.q.y=select(u,s.q.y+u,add);} else if(idx==2u){s.q.z=select(u,s.q.z+u,add);} else if(idx==3u){s.q.w=select(u,s.q.w+u,add);}
  else if(idx==4u){s.v.x=select(u,s.v.x+u,add);} else if(idx==5u){s.v.y=select(u,s.v.y+u,add);} else if(idx==6u){s.v.z=select(u,s.v.z+u,add);} else if(idx==7u){s.v.w=select(u,s.v.w+u,add);}
  else if(idx==8u){s.topo.x=select(u,s.topo.x+u,add);} else if(idx==9u){s.topo.y=select(u,s.topo.y+u,add);} else if(idx==10u){s.topo.z=select(u,s.topo.z+u,add);} else if(idx==11u){s.topo.w=select(u,s.topo.w+u,add);}
  else if(idx==12u){s.outv.x=select(u,s.outv.x+u,add);} else if(idx==13u){s.outv.y=select(u,s.outv.y+u,add);} else if(idx==14u){s.outv.z=select(u,s.outv.z+u,add);} else if(idx==15u){s.outv.w=select(u,s.outv.w+u,add);}
  return s;
}
fn cmpKey(ahi:u32,alo:u32,bhi:u32,blo:u32)->i32 { if(ahi<bhi){return -1;} if(ahi>bhi){return 1;} if(alo<blo){return -1;} if(alo>blo){return 1;} return 0; }
fn findKey(hi:u32,lo:u32)->vec2<u32> { var l=0u; var r=params.cell_count; loop { if(l>=r){break;} let m=l+(r-l)/2u; let c=cells[m]; if(cmpKey(c.head.x,c.head.y,hi,lo)<0){l=m+1u;}else{r=m;} } let ok=select(0u,1u,l<params.cell_count && cmpKey(cells[l].head.x,cells[l].head.y,hi,lo)==0); return vec2<u32>(l,ok); }

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id:vec3<u32>) {
  let gid=id.x; if(gid>=params.state_count){return;} var s=states[gid];
  if((s.outv.w&STATUS_HALT)!=0u || s.topo.w>=params.cell_count){return;}
  let ci=s.topo.w; let c=cells[ci]; let k=packKey(s); let op=c.head.z; let flags=c.head.w;
  let a0=bitcast<i32>(c.args.x); let a1=bitcast<i32>(c.args.y); let a2=bitcast<i32>(c.args.z); let a3=bitcast<i32>(c.args.w);
  if(op==1u){s=setField(s,flags&15u,a0,false);} else if(op==2u){let h=mix32(params.seed^k.x^rotl32(k.y,13u)^s.q.z^c.tail.w); s.topo.z=countOneBits(h)&1u; let delta=select(0u-c.args.x,c.args.x,s.topo.z!=0u); s=setField(s,flags&15u,bitcast<i32>(delta),true);}
  else if(op==3u){s.v+=c.args; s.q+=s.v;} else if(op==4u){let wr=addDivmod(bitcast<i32>(s.q.w),a0,i32(PHI_N)); let w=wr.x; s.q.w=bitcast<u32>(wr.y); if((bitcast<u32>(w)&1u)!=0u&&(flags&(1u<<4u))!=0u){s.topo.x^=1u;} s.outv.w=select(s.outv.w&~STATUS_PHI_WRAP,s.outv.w|STATUS_PHI_WRAP,w!=0); s.topo.z=select(bitcast<u32>(w)&1u,(s.q.w>>11u)&1u,(flags&(1u<<5u))!=0u);}
  else if(op==5u){let wr=addDivmod(bitcast<i32>(s.q.z),a0,i32(TIME_N)); let w=wr.x; s.q.z=bitcast<u32>(wr.y); s.topo.z=bitcast<u32>(w)&1u; if(w!=0){s.outv.x=mix32(s.outv.x^bitcast<u32>(w)^c.tail.w);}}
  else if(op==6u){s.outv.z=0u; s.outv.w|=STATUS_ZERO; s.topo.z=1u;} else if(op==7u){let rho=normi(bitcast<i32>(s.q.x),i32(RHO_N)); let th=normi(bitcast<i32>(s.q.y),i32(THETA_N)); let radial=wideMax(wideSubI32(a0,rho),wideSubI32(rho,a1)); let angular=wideSub(wideAbsI32(cycdelta(th,normi(a2,i32(THETA_N)),i32(THETA_N))),wideAbsI32(a3)); let res=wideMax(radial,angular); let residual=bitcast<i32>(res.lo); s.outv.z=res.lo; s.topo.z=select(0u,1u,residual<=0); s.outv.w=select(s.outv.w&~STATUS_CONE,s.outv.w|STATUS_CONE,residual<=0);}
  else if(op==8u){let rho=normi(bitcast<i32>(s.q.x),i32(RHO_N)); let ph=normi(bitcast<i32>(s.q.w),i32(PHI_N)); var res=wideSub(wideAbs(wideSubI32(rho,a0)),wideAbsI32(a1)); if(a3>=0){let angular=wideSub(wideAbsI32(cycdelta(ph,normi(a2,i32(PHI_N)),i32(PHI_N))),wideAbsI32(a3)); res=wideMax(res,angular);} let residual=bitcast<i32>(res.lo); s.outv.z=res.lo; s.topo.z=select(0u,1u,residual<=0); s.outv.w=select(s.outv.w&~STATUS_SPHERE,s.outv.w|STATUS_SPHERE,residual<=0);}
  else if(op==9u){let rho=bitcast<i32>(s.q.x); let w=floordiv(rho,i32(RHO_N)); s.q.x=bitcast<u32>(rho-w*i32(RHO_N)); let odd=bitcast<u32>(w)&1u; if(odd!=0u){let th=normi(bitcast<i32>(s.q.y),i32(THETA_N)); s.q.y=select(bitcast<u32>(normi(i32(THETA_N/2u)-th,i32(THETA_N))),bitcast<u32>(normi(th+i32(THETA_N/2u),i32(THETA_N))),(flags&1u)!=0u); s.q.w=0u-s.q.w; s.topo.x^=1u; if((flags&2u)!=0u){s.topo.y^=1u;} s.outv.w|=STATUS_WRAP;}else{s.outv.w&=~STATUS_WRAP;} s.topo.z=odd; s=normalized(s);}
  else if(op==10u){if(a0<0 || a0>=64){states[gid]=s; return;} let bi=bitcast<u32>(a0); if(bi<32u){s.topo.z=(k.y>>bi)&1u;}else{s.topo.z=(k.x>>(bi-32u))&1u;}} else if(op==11u){if((s.topo.z&1u)!=0u){s.q+=c.args; if((flags&1u)!=0u){s.topo.x^=1u;} if((flags&2u)!=0u){s.topo.y^=1u;} s=normalized(s);}}
  else if(op==12u){let sh=clamp(a1,0,30); let d=1<<u32(sh); let positive=((s.topo.x^s.topo.z)&1u)!=0u; let turn=select(0u-c.args.x,c.args.x,positive); s.q.w=(s.q.w+turn)&(PHI_N-1u); s.v=vec4<u32>(bitcast<u32>(bitcast<i32>(s.v.x)/d),bitcast<u32>(bitcast<i32>(s.v.y)/d),bitcast<u32>(bitcast<i32>(s.v.z)/d),bitcast<u32>(bitcast<i32>(s.v.w)/d));}
  else if(op==13u){s.outv.y=c.tail.z;} else if(op==14u){s.outv.y=c.tail.z; s.outv.w|=STATUS_EMIT; if((flags&1u)!=0u){s.outv.w|=STATUS_HALT;}} else if(op==15u){s.outv.w|=STATUS_HALT;}
  s=normalized(s); s.outv.x=mix32(s.outv.x^c.tail.z^c.tail.w^k.x^rotl32(k.y,7u)^s.topo.z^ci);
  if((s.outv.w&STATUS_HALT)==0u){if((flags&FLAG_REKEY)!=0u){let nk=packKey(s); let f=findKey(nk.x,nk.y); if(f.y!=0u){s.outv.w&=~STATUS_REKEY_MISS; s.topo.w=f.x;}else{s.outv.w|=STATUS_REKEY_MISS; s.topo.w=select(c.tail.x,c.tail.y,(s.topo.z&1u)!=0u);}}else{s.topo.w=select(c.tail.x,c.tail.y,(s.topo.z&1u)!=0u);}}
  states[gid]=s;
}
