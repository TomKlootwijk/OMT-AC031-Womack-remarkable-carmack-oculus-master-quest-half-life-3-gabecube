package org.atomos.radio;

import android.content.Context;
import android.graphics.*;
import android.view.View;
import java.util.*;

/** Display-only trend, retaining reported dBm values; no resampling is applied to the journal. */
final class TrendView extends View {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private List<double[]> points=Collections.emptyList();
    TrendView(Context c){super(c);setMinimumHeight((int)(220*getResources().getDisplayMetrics().density));}
    void setPoints(List<double[]> values){points=values;invalidate();}
    @Override protected void onDraw(Canvas canvas){super.onDraw(canvas);float d=getResources().getDisplayMetrics().density;float left=48*d,right=getWidth()-18*d,top=20*d,bottom=getHeight()-36*d;paint.setTextSize(11*d);paint.setColor(Ui.MUTED);
        if(points.isEmpty()){canvas.drawText("No numeric signal measurements",left,top+30*d,paint);return;}
        double low=Double.POSITIVE_INFINITY,high=Double.NEGATIVE_INFINITY;for(double[]p:points){low=Math.min(low,p[1]);high=Math.max(high,p[1]);}low=Math.floor(low/5)*5-5;high=Math.ceil(high/5)*5+5;
        double begin=points.get(0)[0],end=points.get(points.size()-1)[0];double duration=Math.max(1,end-begin);
        for(int i=0;i<=4;i++){float y=bottom-(bottom-top)*i/4;paint.setColor(0xffdce7e3);canvas.drawLine(left,y,right,y,paint);paint.setColor(Ui.MUTED);canvas.drawText(String.format(Locale.ROOT,"%.0f",low+(high-low)*i/4),4*d,y+4*d,paint);}
        paint.setColor(Ui.ACCENT);paint.setStrokeWidth(2*d);float priorX=0,priorY=0;boolean first=true;for(double[]p:points){float x=left+(float)((p[0]-begin)/duration)*(right-left);float y=bottom-(float)((p[1]-low)/(high-low))*(bottom-top);if(!first)canvas.drawLine(priorX,priorY,x,y,paint);canvas.drawCircle(x,y,2*d,paint);priorX=x;priorY=y;first=false;}
        paint.setColor(Ui.MUTED);canvas.drawText("dBm",4*d,top-4*d,paint);canvas.drawText(String.format(Locale.ROOT,"%.1f–%.1f s since session start",begin/1e9,end/1e9),left,getHeight()-12*d,paint);
    }
}
