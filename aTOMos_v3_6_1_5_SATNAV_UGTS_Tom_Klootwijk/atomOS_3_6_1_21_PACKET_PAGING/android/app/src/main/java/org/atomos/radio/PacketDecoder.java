package org.atomos.radio;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.math.BigInteger;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Bounded, offline PCAP/PCAPNG metadata decoder. No networking, decryption or stream reassembly. */
public final class PacketDecoder {
    public static final long MAX_FILE_BYTES=64L*1024*1024;
    public static final int MAX_PACKETS=100000,MAX_PACKET_BYTES=1024*1024,MAX_BLOCK_BYTES=16*1024*1024,MAX_DETAILS=200,MAX_ENDPOINTS=512;
    public static final int MAX_UDP_PREVIEW_BYTES=128;
    private PacketDecoder(){}
    public static String decode(File file)throws IOException {
        return decodeInternal(file,new State());
    }
    /** A bounded page over all matching packets in the inspected capture prefix. */
    public static String decodePage(File file,String filter,String query,int offset,int pageSize,String expectedSha)throws IOException {
        if(offset<0||pageSize<1||pageSize>MAX_DETAILS)throw new IllegalArgumentException("offset must be nonnegative; pageSize must be1..200");
        String normalizedFilter=filter==null?"All":filter.trim(),normalizedQuery=query==null?"":query.trim();
        if(!Arrays.asList("All","UDP","DNS","TCP","TLS").contains(normalizedFilter))throw new IllegalArgumentException("unsupported packet filter");
        if(normalizedQuery.length()>256)throw new IllegalArgumentException("query exceeds256 characters");
        String pin=expectedSha==null?"":expectedSha.trim().toLowerCase(Locale.ROOT);if(!pin.isEmpty()&&!pin.matches("[0-9a-f]{64}"))throw new IllegalArgumentException("expectedSha must be a SHA-256 hex string");
        State s=new State();s.paged=true;s.filter=normalizedFilter;s.query=normalizedQuery;s.offset=offset;s.pageSize=pageSize;s.expectedSha=pin;
        return decodeInternal(file,s);
    }
    private static String decodeInternal(File file,State s)throws IOException {
        checkCancelled();s.fileBytes=file.length();
        if(s.fileBytes>MAX_FILE_BYTES){s.issue("file exceeds 64 MiB inspection limit");s.status="limit_exceeded";return s.report().toString();}
        s.sha=hash(file);
        if(s.paged&&!s.expectedSha.isEmpty()&&!s.sha.equals(s.expectedSha)){s.status="source_changed";s.issue("capture SHA-256 no longer matches requested source");return s.report().toString();}
        try(InputStream raw=new BufferedInputStream(new FileInputStream(file))){
            Reader in=new Reader(raw);byte[] magic=in.read(4,false);
            if(magic==null)throw new Bad("empty capture");
            if(hex(magic).equals("0a0d0d0a")){s.format="pcapng";pcapng(in,magic,s);}
            else{String m=hex(magic);if(!Arrays.asList("d4c3b2a1","a1b2c3d4","4d3cb2a1","a1b23c4d").contains(m)){s.status="unsupported";throw new Bad("unrecognized capture magic");}s.format="pcap";pcap(in,m,s);}
            if(s.status.equals("pending")){s.complete=true;s.status=s.issueCount==0&&s.truncated==0?"ok":"partial";}
        }catch(Bad e){if(s.status.equals("pending"))s.status="malformed";s.issue(e.getMessage());}
        if(file.length()!=s.fileBytes || !s.sha.equals(hash(file))){s.complete=false;s.status="source_changed";s.issue("capture bytes changed during inspection");if(s.paged){s.details=new JSONArray();s.matches=0;}}
        checkCancelled();
        return s.report().toString();
    }
    private static void checkCancelled()throws InterruptedIOException {if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("packet inspection cancelled");}
    private static final class Bad extends Exception { Bad(String s){super(s);} }
    private static final class Reader {
        final InputStream in;long offset;Reader(InputStream i){in=i;}
        byte[] read(int n,boolean eof)throws IOException,Bad {
            checkCancelled();
            if(n<0 || n>MAX_BLOCK_BYTES)throw new Bad("invalid bounded read at offset "+offset);
            if(offset+n>MAX_FILE_BYTES)throw new Bad("capture grew beyond 64 MiB limit");
            byte[] b=new byte[n];int p=0;
            while(p<n){checkCancelled();int k=in.read(b,p,n-p);if(k<0){if(p==0&&eof)return null;throw new Bad("truncated capture at offset "+offset+"; needed "+(n-p)+" bytes");}p+=k;offset+=k;}
            return b;
        }
    }
    private static final class Iface {int link;long snap;BigInteger denominator=BigInteger.valueOf(1000000),secondsOffset=BigInteger.ZERO;}
    private static final class State {
        String format="unknown",status="pending",sha;long fileBytes;boolean complete;int packets,decoded,unsupported,malformed,truncated,issueCount,endpointOmitted,blocks,sections,interfacesOmitted;
        boolean paged;String filter="All",query="",expectedSha="";int offset,pageSize=MAX_DETAILS,matches;
        final Map<String,Long> protocols=new TreeMap<>(),layers=new TreeMap<>(),ends=new TreeMap<>();
        JSONArray details=new JSONArray();final JSONArray issues=new JSONArray(),interfaces=new JSONArray();
        void issue(String message){issueCount++;if(issues.length()<100)issues.put(message);}
        void count(Map<String,Long> map,String key){map.put(key,map.getOrDefault(key,0L)+1);}
        void endpoint(String ip,Object port){String k=(ip.indexOf(':')>=0?"["+ip+"]":ip)+(port==null?"":":"+port);if(ends.containsKey(k)||ends.size()<MAX_ENDPOINTS)count(ends,k);else endpointOmitted++;}
        JSONObject report(){JSONObject result=obj("schema","atomos.packet_inspection.v1","format",format,"status",status,"complete",complete,
            "file_bytes",fileBytes,"file_sha256",sha,"packets_seen",packets,"packets_decoded",decoded,"unsupported_packets",unsupported,"malformed_packets",malformed,"capture_truncated_packets",truncated,
            "protocol_counts",new JSONObject(protocols),"layer_counts",new JSONObject(layers),"endpoints",new JSONObject(ends),"endpoint_occurrences_omitted",endpointOmitted,
            "packets",details,"packet_details_omitted",Math.max(0,packets-details.length()),"interfaces",interfaces,"interface_details_omitted",interfacesOmitted,"sections",sections,"blocks_seen",blocks,"issues",issues,"issue_count",issueCount,
            "limits",obj("file_bytes",MAX_FILE_BYTES,"packets",MAX_PACKETS,"captured_packet_bytes",MAX_PACKET_BYTES,"pcapng_block_bytes",MAX_BLOCK_BYTES,"pcapng_blocks",200000,"packet_details",MAX_DETAILS,"endpoints",MAX_ENDPOINTS,"issues",100,"interfaces_per_section",1024,"interface_details",1024,"dns_questions",32,"dns_records",64,"udp_preview_bytes",MAX_UDP_PREVIEW_BYTES,"udp_application_inspection_bytes",4096),
            "semantics",obj("protocol_counts","one deepest recognized protocol per packet; optional UDP application candidates remain UDP","endpoints","packet endpoint occurrences; not unique physical devices","timestamps","capture clock, not synchronized by this decoder","payload_content","bounded raw UDP previews and parsed DNS/DHCP/NTP/HTTP/TLS metadata; previews are not decrypted","tcp_reassembly",false,"ip_fragment_reassembly",false,"checksums_verified",false,"decryption",false));
            if(paged)put(result,"page",obj("offset",offset,"page_size",pageSize,"returned",details.length(),"filter",filter,"query",query,"expected_sha256",expectedSha.isEmpty()?JSONObject.NULL:expectedSha,"total_matches",matches,"has_next",(long)offset+details.length()<matches,"next_offset",(long)offset+details.length()<matches?(long)offset+details.length():JSONObject.NULL,"matches_complete",complete,"valid",!status.equals("source_changed"),"matching_rows_omitted",Math.max(0,matches-details.length()),"search_scope","decoded metadata and bounded raw UDP previews; inspected prefix only"));return result;}
        void packet(byte[] b,int link,long original,Object timestamp,int section,int interfaceId)throws Bad {
            packets++;JSONObject p=obj("index",packets,"linktype",link,"captured_length",b.length,"original_length",original,"capture_truncated",b.length<original,"timestamp",timestamp,"section",section,"interface_id",interfaceId);
            if(b.length<original)truncated++;
            JSONArray ls=new JSONArray();String primary="Unknown",outcome="decoded";
            boolean richDetails=paged?(!query.isEmpty()||(matches>=offset&&details.length()<pageSize)):packets<=MAX_DETAILS;
            try {primary=decodePacket(b,link,p,ls,richDetails);if(primary.startsWith("Unsupported")){outcome="unsupported";unsupported++;issue("packet "+packets+": "+primary);}else decoded++;}
            catch(Bad e){outcome="malformed_or_truncated";malformed++;issue("packet "+packets+": "+e.getMessage());put(p,"error",e.getMessage());primary=ls.length()==0?"Malformed":ls.optString(ls.length()-1);}
            put(p,"status",outcome);put(p,"protocol",primary);put(p,"protocols",ls);count(protocols,primary);for(int i=0;i<ls.length();i++)count(layers,ls.optString(i));
            if(p.has("source_ip")){endpoint(p.optString("source_ip"),p.has("source_port")?p.opt("source_port"):null);endpoint(p.optString("destination_ip"),p.has("destination_port")?p.opt("destination_port"):null);}
            if(paged){if(PacketPresentation.matches(p,filter,query)){if(matches>=offset&&details.length()<pageSize)details.put(p);matches++;}}
            else if(details.length()<MAX_DETAILS)details.put(p);
        }
    }
    private static void pcap(Reader in,String magic,State s)throws IOException,Bad {
        boolean le=magic.equals("d4c3b2a1")||magic.equals("4d3cb2a1"),nano=magic.equals("4d3cb2a1")||magic.equals("a1b23c4d");
        byte[] h=in.read(20,false);need(u16(h,0,le)==2&&u16(h,2,le)==4,"unsupported PCAP version");long snap=u32(h,12,le),network=u32(h,16,le);need(snap>0,"zero PCAP snaplen");
        // Upper linktype flags are retained, never silently interpreted as an ordinary linktype.
        int link=(int)network;s.sections=1;s.interfaces.put(obj("section",0,"interface_id",0,"linktype_unsigned",network,"snaplen",snap,"timestamp_denominator",nano?"1000000000":"1000000"));
        while(true){byte[] ph=in.read(16,true);if(ph==null)return;if(s.packets>=MAX_PACKETS){s.status="limit_exceeded";s.issue("packet inspection limit reached");return;}
            long secs=u32(ph,0,le),fraction=u32(ph,4,le),cap=u32(ph,8,le),orig=u32(ph,12,le);
            need(cap<=MAX_PACKET_BYTES,"PCAP packet exceeds 1 MiB limit");need(cap<=snap&&cap<=orig,"inconsistent PCAP captured length");need(fraction<(nano?1000000000L:1000000L),"PCAP timestamp fraction out of range");
            BigInteger den=BigInteger.valueOf(nano?1000000000L:1000000L),ticks=BigInteger.valueOf(secs).multiply(den).add(BigInteger.valueOf(fraction));
            s.packet(in.read((int)cap,false),link,orig,time(ticks,den),0,0);
        }
    }
    private static void pcapng(Reader in,byte[] first,State s)throws IOException,Bad {
        boolean le=true;boolean section=false;ArrayList<Iface> ifaces=new ArrayList<>();byte[] type=first;
        while(type!=null){if(s.blocks>=200000){s.status="limit_exceeded";s.issue("PCAPNG block inspection limit reached");return;}s.blocks++;byte[] length=in.read(4,false);boolean shb=hex(type).equals("0a0d0d0a");byte[] bom=null;
            if(shb){bom=in.read(4,false);String m=hex(bom);need(m.equals("4d3c2b1a")||m.equals("1a2b3c4d"),"PCAPNG invalid byte-order magic");le=m.equals("4d3c2b1a");}
            need(shb||section,"PCAPNG block before section header");long len=u32(length,0,le);need(len>=12&&len%4==0&&len<=MAX_BLOCK_BYTES,"invalid PCAPNG block length at offset "+(in.offset-8));
            need(!shb||len>=28,"PCAPNG section header too short");byte[] body;
            if(shb){byte[] rest=in.read((int)len-12,false);body=new byte[(int)len-8];System.arraycopy(bom,0,body,0,4);System.arraycopy(rest,0,body,4,rest.length);}
            else body=in.read((int)len-8,false);
            need(u32(body,body.length-4,le)==len,"PCAPNG block trailer length mismatch");int end=body.length-4;long bt=u32(type,0,le);
            if(shb){need(u16(body,4,le)==1,"unsupported PCAPNG major version");need(i64(body,8,le)>=-1,"invalid PCAPNG section length");section=true;ifaces.clear();s.sections++;}
            else if(bt==1){need(end>=8,"PCAPNG interface block truncated");need(ifaces.size()<1024,"too many PCAPNG interfaces");Iface f=new Iface();f.link=u16(body,0,le);f.snap=u32(body,4,le);
                int pos=8;while(pos<end){need(end-pos>=4,"PCAPNG option header truncated");int code=u16(body,pos,le),n=u16(body,pos+2,le);pos+=4;need(n<=end-pos,"PCAPNG option value truncated");if(code==0){need(n==0,"invalid end-of-options length");break;}
                    if(code==9){need(n==1,"invalid if_tsresol length");int v=body[pos]&255;f.denominator=BigInteger.valueOf((v&128)==0?10:2).pow(v&127);}
                    if(code==14){need(n==8,"invalid if_tsoffset length");f.secondsOffset=BigInteger.valueOf(i64(body,pos,le));}pos+=((n+3)/4)*4;need(pos<=end,"PCAPNG option padding truncated");}
                ifaces.add(f);if(s.interfaces.length()<1024)s.interfaces.put(obj("section",s.sections-1,"interface_id",ifaces.size()-1,"linktype",f.link,"snaplen",f.snap,"timestamp_denominator",f.denominator.toString(),"timestamp_offset_seconds",f.secondsOffset.toString()));else s.interfacesOmitted++;
            }else if(bt==6||bt==2||bt==3){
                if(s.packets>=MAX_PACKETS){s.status="limit_exceeded";s.issue("packet inspection limit reached");return;}
                int id,data;long cap,orig;Object timestamp=JSONObject.NULL;
                if(bt==3){need(end>=4,"PCAPNG simple packet block truncated");id=0;need(!ifaces.isEmpty(),"PCAPNG simple packet lacks interface 0");orig=u32(body,0,le);Iface f=ifaces.get(0);cap=f.snap==0?orig:Math.min(orig,f.snap);data=4;need(end-data==((cap+3)/4)*4,"PCAPNG simple packet padding/length mismatch");}
                else{need(end>=20,"PCAPNG packet block truncated");long rawId=bt==2?u16(body,0,le):u32(body,0,le);need(rawId<ifaces.size(),"PCAPNG packet references unknown interface "+rawId);id=(int)rawId;cap=u32(body,12,le);orig=u32(body,16,le);data=20;Iface f=ifaces.get(id);BigInteger ticks=BigInteger.valueOf(u32(body,4,le)).shiftLeft(32).add(BigInteger.valueOf(u32(body,8,le)));timestamp=time(ticks.add(f.secondsOffset.multiply(f.denominator)),f.denominator);}
                need(id<ifaces.size(),"PCAPNG packet references unknown interface");Iface f=ifaces.get(id);need(cap<=MAX_PACKET_BYTES,"PCAPNG packet exceeds 1 MiB limit");need(cap<=orig&&(f.snap==0||cap<=f.snap),"inconsistent PCAPNG captured length");need(data+((cap+3)/4)*4<=end,"PCAPNG packet data truncated");
                s.packet(Arrays.copyOfRange(body,data,data+(int)cap),f.link,orig,timestamp,s.sections-1,id);
            }else if(bt!=4&&bt!=5){s.issue("unsupported PCAPNG block type "+bt+" skipped");}
            type=in.read(4,true);
        }
    }
    private static JSONObject time(BigInteger ticks,BigInteger denominator){BigInteger[] q=ticks.multiply(BigInteger.valueOf(1000000000)).divideAndRemainder(denominator);return obj("seconds_numerator",ticks.toString(),"seconds_denominator",denominator.toString(),"nanoseconds_exact",q[1].signum()==0?q[0].toString():JSONObject.NULL);}
    private static String decodePacket(byte[] b,int link,JSONObject p,JSONArray ls,boolean richDetails)throws Bad {
        int pos=0,ether=0;
        if(link==1){need(b.length>=14,"Ethernet header truncated");ls.put("Ethernet");put(p,"source_mac",mac(b,6));put(p,"destination_mac",mac(b,0));ether=u16(b,12,false);pos=14;int count=0;JSONArray vlans=new JSONArray();while(ether==0x8100||ether==0x88a8||ether==0x9100){need(++count<=4,"VLAN depth exceeds 4");need(b.length-pos>=4,"VLAN header truncated");int tci=u16(b,pos,false);vlans.put(obj("tpid",ether,"tci",tci,"vid",tci&4095));ether=u16(b,pos+2,false);pos+=4;}if(count>0){ls.put("VLAN");put(p,"vlans",vlans);}}
        else if(link==101||link==228||link==229){need(b.length>0,"empty raw IP packet");ls.put("RAW");int version=(b[0]&255)>>4;ether=version==4?0x800:version==6?0x86dd:0;need(link!=228||version==4,"IPv4 linktype contains wrong version");need(link!=229||version==6,"IPv6 linktype contains wrong version");}
        else if(link==113){need(b.length>=16,"Linux SLL header truncated");ls.put("LinuxSLL");ether=u16(b,14,false);pos=16;}
        else if(link==276){need(b.length>=20,"Linux SLL2 header truncated");ls.put("LinuxSLL2");ether=u16(b,0,false);pos=20;}
        else return "Unsupported linktype "+Integer.toUnsignedString(link);
        put(p,"ether_type",ether);int end,proto;boolean fragment=false;
        if(ether==0x800){ls.put("IPv4");need(b.length-pos>=20,"IPv4 header truncated");need((b[pos]&255)>>4==4,"invalid IPv4 version");int header=(b[pos]&15)*4,total=u16(b,pos+2,false);need(header>=20&&total>=header,"invalid IPv4 lengths");need(b.length-pos>=header,"IPv4 options truncated");end=Math.min(b.length,pos+total);put(p,"network_truncated",pos+total>b.length);put(p,"source_ip",address(b,pos+12,4));put(p,"destination_ip",address(b,pos+16,4));int frag=u16(b,pos+6,false);fragment=(frag&0x3fff)!=0;put(p,"fragment_offset_bytes",(frag&0x1fff)*8);put(p,"more_fragments",(frag&0x2000)!=0);proto=b[pos+9]&255;pos+=header;if((frag&0x1fff)!=0){put(p,"fragment_reassembly_required",true);return "IPv4 fragment";}}
        else if(ether==0x86dd){ls.put("IPv6");need(b.length-pos>=40,"IPv6 header truncated");need((b[pos]&255)>>4==6,"invalid IPv6 version");int length=u16(b,pos+4,false);end=Math.min(b.length,pos+40+length);put(p,"network_truncated",pos+40+length>b.length);put(p,"source_ip",address(b,pos+8,16));put(p,"destination_ip",address(b,pos+24,16));proto=b[pos+6]&255;pos+=40;if(length==0&&b.length>pos&&proto!=59)return "Unsupported IPv6 jumbogram";
            int ext=0;while(proto==0||proto==43||proto==60||proto==44||proto==51){need(++ext<=8,"IPv6 extension depth exceeds 8");need(end-pos>=2,"IPv6 extension header truncated");int next=b[pos]&255,n;
                if(proto==44){n=8;need(end-pos>=n,"IPv6 fragment header truncated");int f=u16(b,pos+2,false);fragment=true;put(p,"fragment_offset_bytes",f&0xfff8);put(p,"more_fragments",(f&1)!=0);if((f&0xfff8)!=0){put(p,"fragment_reassembly_required",true);return "IPv6 fragment";}}
                else n=proto==51?((b[pos+1]&255)+2)*4:((b[pos+1]&255)+1)*8;need(end-pos>=n,"IPv6 extension body truncated");pos+=n;proto=next;}
        }else if(ether==0x806){ls.put("ARP");return "ARP";}else return "Unsupported EtherType "+ether;
        put(p,"ip_protocol",proto);if(proto==50){ls.put("ESP");put(p,"encrypted",JSONObject.NULL);put(p,"payload_opaque",true);return "ESP";}if(proto==59)return "IPv6 no next header";
        if(proto==17){ls.put("UDP");need(end-pos>=8,"UDP header truncated");int src=u16(b,pos,false),dst=u16(b,pos+2,false),n=u16(b,pos+4,false);need(n>=8,"invalid UDP length");put(p,"source_port",src);put(p,"destination_port",dst);put(p,"udp_length",n);boolean shortPayload=n>end-pos;put(p,"transport_payload_incomplete",shortPayload||fragment);int payloadEnd=Math.min(end,pos+n);
            if(richDetails)udpPreview(b,pos,payloadEnd,n,!shortPayload&&!fragment,p);
            if(!shortPayload&&!fragment){if(src==53||dst==53||src==5353||dst==5353){ls.put("DNS");put(p,"dns",dns(b,pos+8,payloadEnd));return "DNS";}
                if(richDetails){JSONObject application=udpApplication(b,pos+8,payloadEnd,src,dst);if(application!=null)put(p,"udp_application",application);}}
            return "UDP";}
        if(proto==6){ls.put("TCP");need(end-pos>=20,"TCP header truncated");int src=u16(b,pos,false),dst=u16(b,pos+2,false),n=((b[pos+12]&255)>>4)*4;need(n>=20&&end-pos>=n,"TCP options/header truncated");put(p,"source_port",src);put(p,"destination_port",dst);put(p,"tcp_flags",b[pos+13]&255);put(p,"tcp_sequence",u32(b,pos+4,false));int payload=pos+n;
            if(fragment){put(p,"transport_payload_incomplete",true);return "TCP";}
            if(src==53||dst==53){if(end-payload>=2){int length=u16(b,payload,false);if(length<=end-payload-2){ls.put("DNS");put(p,"dns",dns(b,payload+2,payload+2+length));return "DNS";}put(p,"stream_reassembly_required",true);}return "TCP";}
            String http=http(b,payload,end,p);if(http!=null){ls.put("HTTP");return "HTTP";}
            if(end-payload>=5){int type=b[payload]&255,major=b[payload+1]&255,minor=b[payload+2]&255,len=u16(b,payload+3,false);if(type>=20&&type<=24&&major==3&&minor<=4){ls.put("TLS");JSONObject tls=obj("record_type",type,"record_version_major",major,"record_version_minor",minor,"declared_record_length",len,"record_complete",len<=end-payload-5,"identification","record-header heuristic; no reassembly/decryption","encryption_state","not established from record header");if(type==22&&len>=4&&end-payload>=9){int ht=b[payload+5]&255,hl=((b[payload+6]&255)<<16)|((b[payload+7]&255)<<8)|(b[payload+8]&255);if((ht==1||ht==2)&&hl<=len-4){put(tls,"handshake_type",ht);put(tls,"handshake_type_scope","candidate unprotected Hello header; unauthenticated");}}put(p,"tls",tls);put(p,"encrypted",JSONObject.NULL);put(p,"payload_opaque",true);put(p,"stream_reassembly_required",len>end-payload-5);return "TLS";}}
            return "TCP";}
        if(proto==1||proto==58){String name=proto==1?"ICMP":"ICMPv6";ls.put(name);need(end-pos>=4,name+" header truncated");put(p,"icmp_type",b[pos]&255);put(p,"icmp_code",b[pos+1]&255);return name;}
        return "Unsupported IP protocol "+proto;
    }
    private static void udpPreview(byte[] b,int start,int end,int declared,boolean complete,JSONObject p){
        int payload=start+8,captured=end-payload,shown=Math.min(captured,MAX_UDP_PREVIEW_BYTES);
        put(p,"udp_checksum_hex",String.format(Locale.ROOT,"%04x",u16(b,start+6,false)));put(p,"udp_checksum_verified",false);
        put(p,"udp_payload_declared_bytes",declared-8);put(p,"udp_payload_captured_bytes",captured);put(p,"udp_payload_complete",complete);
        put(p,"udp_payload_preview_bytes",shown);put(p,"udp_payload_preview_truncated",shown<captured);
        put(p,"udp_payload_hex",hex(Arrays.copyOfRange(b,payload,payload+shown)));put(p,"udp_payload_text",escapedAscii(b,payload,payload+shown));
        put(p,"udp_payload_text_encoding","escaped ASCII view of raw bytes; not decrypted");
    }
    private static String escapedAscii(byte[] b,int start,int end){StringBuilder s=new StringBuilder();for(int i=start;i<end;i++){int c=b[i]&255;
        if(c=='\\')s.append("\\\\");else if(c==10)s.append("\\n");else if(c==13)s.append("\\r");else if(c==9)s.append("\\t");else if(c>=32&&c<=126)s.append((char)c);else s.append(String.format(Locale.ROOT,"\\x%02x",c));}return s.toString();}
    /** Candidate application headers require both conventional ports and matching wire structure. */
    private static JSONObject udpApplication(byte[] b,int start,int end,int src,int dst)throws Bad {
        int n=end-start;
        // RFC 5905 common 48-byte time header. Modes 6/7 use other formats.
        if((src==123||dst==123)&&n>=48){int first=b[start]&255,version=(first>>3)&7,mode=first&7,stratum=b[start+1]&255;
            if((version==3||version==4)&&mode>=1&&mode<=5&&stratum<=16){
                JSONObject d=obj("protocol","NTP","identification","candidate standard time header; unauthenticated","version",version,"mode",mode,"leap_indicator",first>>6,"stratum",stratum,"poll_exponent",(int)b[start+2],"precision_exponent",(int)b[start+3],"reference_id_hex",hex(Arrays.copyOfRange(b,start+12,start+16)),"extension_or_authentication_bytes",n-48,"authentication_verified",false);
                put(d,"root_delay_seconds",obj("numerator",Integer.toString((int)u32(b,start+4,false)),"denominator","65536"));
                put(d,"root_dispersion_seconds",obj("numerator",Long.toString(u32(b,start+8,false)),"denominator","65536"));
                String[] names={"reference_timestamp","origin_timestamp","receive_timestamp","transmit_timestamp"};for(int i=0;i<4;i++){int pos=start+16+i*8;long secs=u32(b,pos,false),fraction=u32(b,pos+4,false);put(d,names[i],obj("seconds_field",Long.toString(secs),"fraction_field",Long.toString(fraction),"fraction_denominator","4294967296","zero_field",secs==0&&fraction==0,"era",JSONObject.NULL));}
                put(d,"timestamp_semantics","NTP era-relative wire fields; zero means undefined; era and UTC not inferred");return d;
            }
        }
        // RFC 2131/2132 fixed BOOTP header, magic cookie and bounded TLVs.
        if((src==67||src==68||dst==67||dst==68)&&n>=240&&(b[start]==1||b[start]==2)&&(b[start+2]&255)<=16&&u32(b,start+236,false)==0x63825363L){
            JSONObject d=obj("protocol","BOOTP/DHCP","identification","candidate BOOTP header with DHCP cookie; unauthenticated","op",b[start]&255,"hardware_type",b[start+1]&255,"hardware_address_length",b[start+2]&255,"transaction_id_hex",hex(Arrays.copyOfRange(b,start+4,start+8)),"elapsed_seconds",u16(b,start+8,false),"broadcast_flag",(u16(b,start+10,false)&0x8000)!=0,"client_ip",address(b,start+12,4),"assigned_ip",address(b,start+16,4),"server_ip",address(b,start+20,4),"relay_ip",address(b,start+24,4));
            put(d,"client_hardware_hex",hex(Arrays.copyOfRange(b,start+28,start+28+(b[start+2]&255))));JSONArray options=new JSONArray();put(d,"options",options);int pos=start+240,limit=Math.min(end,start+4096),steps=0;boolean ended=false;String error=null;
            while(pos<limit&&steps++<64){int code=b[pos++]&255;if(code==0)continue;if(code==255){ended=true;break;}if(pos>=limit){error="option length truncated";break;}int len=b[pos++]&255;if(len>limit-pos){error=limit<end?"option inspection limit reached":"option value truncated";break;}JSONObject option=obj("code",code,"length",len);
                if(code==53){if(len!=1){error="DHCP message type length is not 1";break;}int type=b[pos]&255;String[] labels={"Unknown","Discover","Offer","Request","Decline","ACK","NAK","Release","Inform"};put(option,"message_type",type);put(option,"label",type<labels.length?labels[type]:"Unknown");put(d,"message_type",type);put(d,"message_type_label",type<labels.length?labels[type]:"Unknown");put(d,"protocol","DHCP");}
                else if((code==1||code==50||code==54)&&len==4)put(option,"address",address(b,pos,4));
                else if((code==51||code==58||code==59)&&len==4)put(option,"seconds",Long.toString(u32(b,pos,false)));
                else if(code==12||code==15)put(option,"text",escapedAscii(b,pos,pos+Math.min(len,128)));
                else if(code==52&&len==1){put(option,"overload",b[pos]&255);put(d,"overloaded_fields_decoded",false);}
                options.put(option);pos+=len;
            }
            put(d,"options_end_found",ended);put(d,"options_status",error!=null?error:ended?"bounded options parsed":pos<end?"option inspection limit reached":"missing end option");return d;
        }
        return null;
    }
    private static String http(byte[] b,int start,int end,JSONObject p){int stop=-1;for(int i=start;i+1<Math.min(end,start+512);i++)if(b[i]==13&&b[i+1]==10){stop=i;break;}if(stop<0)return null;String line=new String(b,start,stop-start,StandardCharsets.US_ASCII);String[] bits=line.split(" ",3);if(bits.length<2)return null;
        if(bits[0].matches("HTTP/1\\.[01]")&&bits[1].matches("[1-5][0-9][0-9]")){put(p,"http",obj("kind","response","version",bits[0],"status_code",Integer.parseInt(bits[1])));return "HTTP";}
        if(bits.length==3&&Arrays.asList("GET","HEAD","POST","PUT","DELETE","CONNECT","OPTIONS","TRACE","PATCH").contains(bits[0])&&bits[2].matches("HTTP/1\\.[01]")){put(p,"http",obj("kind","request","method",bits[0],"version",bits[2],"request_target_omitted",true));return "HTTP";}return null;}
    private static final class Name {String value;int next;Name(String v,int n){value=v;next=n;}}
    private static Name name(byte[] b,int base,int pos,int end)throws Bad {
        StringBuilder value=new StringBuilder();Set<Integer> seen=new HashSet<>();int next=-1,wireLength=1;
        for(int steps=0;steps<128;steps++){need(pos<end,"DNS name truncated");need(seen.add(pos),"DNS compression pointer loop");int n=b[pos]&255;
            if(n==0)return new Name(value.length()==0?".":value.toString(),next<0?pos+1:next);
            if((n&0xc0)==0xc0){need(pos+1<end,"DNS pointer truncated");int target=base+((n&63)<<8)+(b[pos+1]&255);need(target>=base&&target<end,"DNS pointer outside message");if(next<0)next=pos+2;pos=target;continue;}
            need((n&0xc0)==0&&n<=63,"invalid DNS label length");need(pos+1+n<=end,"DNS label truncated");wireLength+=n+1;need(wireLength<=255,"DNS expanded name exceeds 255 octets");if(value.length()>0)value.append('.');for(int i=0;i<n;i++){int c=b[pos+1+i]&255;if(c>=33&&c<=126&&c!='.'&&c!='\\')value.append((char)c);else value.append(String.format(Locale.ROOT,"\\x%02x",c));}pos+=n+1;
        }throw new Bad("DNS name exceeds pointer/label traversal limit");
    }
    private static JSONObject dns(byte[] b,int base,int end)throws Bad {
        need(end-base>=12,"DNS header truncated");int flags=u16(b,base+2,false),qd=u16(b,base+4,false),an=u16(b,base+6,false),ns=u16(b,base+8,false),ar=u16(b,base+10,false),pos=base+12;
        JSONObject d=obj("id",u16(b,base,false),"response",(flags&0x8000)!=0,"opcode",(flags>>11)&15,"rcode",flags&15,"truncated_flag",(flags&0x200)!=0,"question_count",qd,"answer_count",an,"authority_count",ns,"additional_count",ar);JSONArray questions=new JSONArray(),records=new JSONArray();put(d,"questions",questions);put(d,"records",records);
        if(qd>32){put(d,"detail_limited",true);return d;}
        for(int i=0;i<qd;i++){Name n=name(b,base,pos,end);pos=n.next;need(end-pos>=4,"DNS question fields truncated");questions.put(obj("name",n.value,"type",u16(b,pos,false),"class",u16(b,pos+2,false)));pos+=4;}
        int all=an+ns+ar;for(int i=0;i<Math.min(64,all);i++){Name n=name(b,base,pos,end);pos=n.next;need(end-pos>=10,"DNS resource record header truncated");int type=u16(b,pos,false),cls=u16(b,pos+2,false),len=u16(b,pos+8,false);long ttl=u32(b,pos+4,false);pos+=10;need(end-pos>=len,"DNS resource data truncated");JSONObject rec=obj("section",i<an?"answer":i<an+ns?"authority":"additional","name",n.value,"type",type,"class",cls,"ttl_seconds",ttl,"data_length",len);
            if(type==1&&len==4)put(rec,"address",address(b,pos,4));else if(type==28&&len==16)put(rec,"address",address(b,pos,16));else if(type==5||type==2||type==12){Name target=name(b,base,pos,end);need(target.next<=pos+len,"DNS name exceeds resource-data boundary");put(rec,"target_name",target.value);}records.put(rec);pos+=len;}
        put(d,"detail_limited",all>64);return d;
    }
    private static String address(byte[] b,int pos,int size)throws Bad {try{return InetAddress.getByAddress(Arrays.copyOfRange(b,pos,pos+size)).getHostAddress();}catch(Exception e){throw new Bad("invalid address bytes");}}
    private static String mac(byte[] b,int pos){StringBuilder s=new StringBuilder();for(int i=0;i<6;i++){if(i>0)s.append(':');s.append(String.format(Locale.ROOT,"%02x",b[pos+i]&255));}return s.toString();}
    private static int u16(byte[] b,int p,boolean le){return le?(b[p]&255)|((b[p+1]&255)<<8):((b[p]&255)<<8)|(b[p+1]&255);}
    private static long u32(byte[] b,int p,boolean le){long n=0;for(int i=0;i<4;i++)n=(n<<8)|(b[p+(le?3-i:i)]&255);return n;}
    private static long i64(byte[] b,int p,boolean le){long n=0;for(int i=0;i<8;i++)n=(n<<8)|(b[p+(le?7-i:i)]&255);return n;}
    private static void need(boolean ok,String s)throws Bad {if(!ok)throw new Bad(s);}
    private static JSONObject obj(Object...kv){JSONObject o=new JSONObject();try{for(int i=0;i<kv.length;i+=2)o.put((String)kv[i],kv[i+1]==null?JSONObject.NULL:kv[i+1]);}catch(Exception e){throw new IllegalArgumentException(e);}return o;}
    private static void put(JSONObject o,String key,Object value){try{o.put(key,value==null?JSONObject.NULL:value);}catch(Exception e){throw new IllegalArgumentException(e);}}
    private static String hash(File f)throws IOException {checkCancelled();try{MessageDigest d=MessageDigest.getInstance("SHA-256");try(InputStream in=new BufferedInputStream(new FileInputStream(f))){byte[] b=new byte[65536];int n;long total=0;while((n=in.read(b))!=-1){checkCancelled();total+=n;if(total>MAX_FILE_BYTES)throw new IOException("capture grew beyond 64 MiB limit");d.update(b,0,n);}}checkCancelled();return hex(d.digest());}catch(java.security.NoSuchAlgorithmException e){throw new AssertionError(e);}}
    private static String hex(byte[] b){StringBuilder s=new StringBuilder();for(byte v:b)s.append(String.format(Locale.ROOT,"%02x",v&255));return s.toString();}
}
