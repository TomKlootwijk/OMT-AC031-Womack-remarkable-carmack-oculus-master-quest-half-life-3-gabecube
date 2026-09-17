package org.atomos.radio;

import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/** Bounded decoding of Android-exposed IE bodies, not reconstruction of 802.11 frames. */
public final class WifiIeDecoder {
    private WifiIeDecoder() {}
    public static String decode(int id,int idExt,byte[] bytes) {
        JSONObject fields=new JSONObject(); JSONArray issues=new JSONArray();
        String label=label(id,idExt), status="decoded";
        byte[] b=bytes==null?new byte[0]:bytes;
        try {
            if(bytes==null)throw new IllegalArgumentException("missing IE body");
            if(id<0 || id>255 || idExt<0 || idExt>255)throw new IllegalArgumentException("element ID outside byte range");
            if(b.length>4096)throw new IllegalArgumentException("IE body exceeds 4096-byte decoder limit");
            switch(id) {
                case 0:
                    require(b.length<=32,"SSID exceeds 32 octets");
                    try { fields.put("ssid_utf8",StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(b)).toString()); }
                    catch(CharacterCodingException e){fields.put("ssid_utf8",JSONObject.NULL);fields.put("encoding","non-UTF-8 SSID bytes");}
                    fields.put("hidden_or_empty",b.length==0);break;
                case 1: case 50:
                    require(b.length>=1 && (id!=1 || b.length<=8),"invalid supported-rates length");
                    JSONArray rates=new JSONArray();
                    for(byte v:b)rates.put(object("rate_500_kbps",v&127,"basic",(v&128)!=0));
                    fields.put("rates",rates);break;
                case 3: require(b.length==1,"DS parameter set must contain one octet");fields.put("channel",b[0]&255);break;
                case 48: decodeRsn(b,fields);break;
                case 221:
                    require(b.length>=3,"vendor-specific IE missing OUI");
                    fields.put("oui",oui(b,0)); fields.put("vendor_type",b.length>3?b[3]&255:JSONObject.NULL);
                    fields.put("vendor_identity","not resolved from OUI");break;
                case 45: case 61: case 191: case 192: case 255:
                    status="label_only"; fields.put("capabilities_parsed",false);break;
                default: status="unsupported";
            }
        } catch(Exception e){status="malformed";issues.put(e.getMessage()==null?e.getClass().getSimpleName():e.getMessage());}
        return object("schema","atomos.wifi_ie.v1","id",id,"id_ext",idExt,"length",b.length,
            "status",status,"label",label,"fields",fields,"issues",issues).toString();
    }
    private static String label(int id,int ext){
        switch(id){case 0:return "SSID";case 1:return "Supported rates";case 3:return "DS parameter set";
            case 45:return "HT capabilities";case 48:return "RSN";case 50:return "Extended supported rates";
            case 61:return "HT operation";case 191:return "VHT capabilities";case 192:return "VHT operation";
            case 221:return "Vendor-specific";case 255:switch(ext){case 35:return "HE capabilities";case 36:return "HE operation";case 106:return "EHT operation";case 108:return "EHT capabilities";default:return "Extension element "+ext;}default:return "Element "+id;}
    }
    private static void decodeRsn(byte[] b,JSONObject out)throws Exception {
        require(b.length>=2,"RSN version truncated");int p=0,version=u16(b,p);p+=2;out.put("version",version);
        require(version==1,"unsupported RSN version "+version);
        require(b.length-p>=6,"RSN group cipher/pairwise count truncated");out.put("group_cipher",suite(b,p,false));p+=4;
        int n=u16(b,p);p+=2;require(n>=1 && n<=64 && b.length-p>=4*n,"RSN pairwise suites truncated or exceed 64-entry limit");
        JSONArray pairs=new JSONArray();for(int i=0;i<n;i++,p+=4)pairs.put(suite(b,p,false));out.put("pairwise_ciphers",pairs);
        require(b.length-p>=2,"RSN AKM count truncated");n=u16(b,p);p+=2;
        require(n>=1 && n<=64 && b.length-p>=4*n,"RSN AKM suites truncated or exceed 64-entry limit");
        JSONArray akms=new JSONArray();for(int i=0;i<n;i++,p+=4)akms.put(suite(b,p,true));out.put("akm_suites",akms);
        if(p==b.length)return;require(b.length-p>=2,"RSN capabilities truncated");int caps=u16(b,p);p+=2;
        out.put("capabilities",caps);out.put("management_frame_protection_required",(caps&64)!=0);out.put("management_frame_protection_capable",(caps&128)!=0);
        if(p==b.length)return;require(b.length-p>=2,"RSN PMKID count truncated");n=u16(b,p);p+=2;
        require(n<=64 && b.length-p>=16*n,"RSN PMKIDs truncated or exceed 64-entry limit");out.put("pmkid_count",n);p+=16*n;
        if(p==b.length)return;require(b.length-p>=4,"RSN group management cipher truncated");out.put("group_management_cipher",suite(b,p,false));p+=4;
        out.put("unparsed_trailing_octets",b.length-p);
    }
    private static JSONObject suite(byte[] b,int p,boolean akm){
        int type=b[p+3]&255;String name="unknown suite";
        if((b[p]&255)==0 && (b[p+1]&255)==15 && (b[p+2]&255)==172){
            if(akm){switch(type){case 1:name="802.1X";break;case 2:name="PSK";break;case 3:name="FT-802.1X";break;case 4:name="FT-PSK";break;case 5:name="802.1X-SHA256";break;case 6:name="PSK-SHA256";break;case 8:name="SAE";break;case 9:name="FT-SAE";break;case 11:name="802.1X-Suite-B";break;case 12:name="802.1X-Suite-B-192";break;case 13:name="FT-802.1X-SHA384";break;case 18:name="OWE";break;}}
            else{switch(type){case 0:name="use-group";break;case 1:name="WEP-40";break;case 2:name="TKIP";break;case 4:name="CCMP-128";break;case 5:name="WEP-104";break;case 6:name="BIP-CMAC-128";break;case 8:name="GCMP-128";break;case 9:name="GCMP-256";break;case 10:name="CCMP-256";break;case 11:name="BIP-GMAC-128";break;case 12:name="BIP-GMAC-256";break;case 13:name="BIP-CMAC-256";break;}}
        }
        return object("oui",oui(b,p),"type",type,"label",name);
    }
    private static String oui(byte[] b,int p){return String.format(Locale.ROOT,"%02x:%02x:%02x",b[p]&255,b[p+1]&255,b[p+2]&255);}
    private static int u16(byte[] b,int p){return (b[p]&255)|((b[p+1]&255)<<8);}
    private static void require(boolean ok,String message){if(!ok)throw new IllegalArgumentException(message);}
    private static JSONObject object(Object...kv){JSONObject o=new JSONObject();try{for(int i=0;i<kv.length;i+=2)o.put((String)kv[i],kv[i+1]==null?JSONObject.NULL:kv[i+1]);}catch(Exception e){throw new IllegalArgumentException(e);}return o;}
}
