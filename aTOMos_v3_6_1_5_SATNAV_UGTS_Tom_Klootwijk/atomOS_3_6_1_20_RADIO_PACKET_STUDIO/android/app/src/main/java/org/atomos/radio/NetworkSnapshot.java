package org.atomos.radio;

import android.content.Context;
import android.net.*;
import org.json.*;
import java.net.InetAddress;
import java.util.*;

/** Read-only context for this phone's Android-visible links. No socket or network probe is sent. */
final class NetworkSnapshot {
    private NetworkSnapshot() {}
    @SuppressWarnings("deprecation")
    static JSONObject read(Context context) {
        ConnectivityManager cm=(ConnectivityManager)context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if(cm==null)return Json.object("networks",new JSONArray(),"available",false);
        Network active=cm.getActiveNetwork(); JSONArray rows=new JSONArray();
        Network[] networks=cm.getAllNetworks(); Arrays.sort(networks,Comparator.comparing(Network::toString));
        for(Network network:networks) {
            NetworkCapabilities capabilities=cm.getNetworkCapabilities(network);
            LinkProperties link=cm.getLinkProperties(network);
            JSONArray transports=new JSONArray(),addresses=new JSONArray(),dns=new JSONArray(),routes=new JSONArray();
            if(capabilities!=null) {
                if(capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI))transports.put("WIFI");
                if(capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR))transports.put("CELLULAR");
                if(capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET))transports.put("ETHERNET");
                if(capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN))transports.put("VPN");
                if(capabilities.hasTransport(NetworkCapabilities.TRANSPORT_BLUETOOTH))transports.put("BLUETOOTH");
            }
            if(link!=null) {
                for(LinkAddress address:link.getLinkAddresses())addresses.put(address.toString());
                for(InetAddress address:link.getDnsServers())dns.put(address.getHostAddress());
                for(RouteInfo route:link.getRoutes())routes.put(Json.object("destination",route.getDestination().toString(),"gateway",route.getGateway()==null?null:route.getGateway().getHostAddress(),"interface",route.getInterface(),"default",route.isDefaultRoute()));
            }
            rows.put(Json.object("network_id",network.toString(),"default",network.equals(active),"transports",transports,
                "interface",link==null?null:link.getInterfaceName(),"own_addresses",addresses,"dns_servers",dns,"routes",routes,
                "private_dns_active",link==null?null:link.isPrivateDnsActive(),"private_dns_server",link==null?null:link.getPrivateDnsServerName(),
                "validated",capabilities==null?null:capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED),
                "metered",capabilities==null?null:!capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)));
        }
        return Json.object("available",true,"networks",rows,"scope","this_phone_visible_links","active_probing",false);
    }
}
