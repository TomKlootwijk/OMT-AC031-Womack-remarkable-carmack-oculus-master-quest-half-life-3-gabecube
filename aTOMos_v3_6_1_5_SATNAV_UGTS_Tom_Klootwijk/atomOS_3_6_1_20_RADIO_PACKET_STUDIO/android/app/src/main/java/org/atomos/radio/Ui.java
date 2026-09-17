package org.atomos.radio;

import android.app.Activity;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.*;
import android.widget.*;

final class Ui {
    static final int INK=0xff15312f, MUTED=0xff536966, ACCENT=0xff236a60;
    private Ui(){}
    static int dp(Activity a,int value){return Math.round(value*a.getResources().getDisplayMetrics().density);}
    static LinearLayout page(Activity a,String title,String subtitle){
        ScrollView scroll=new ScrollView(a);scroll.setFillViewport(true);
        LinearLayout page=new LinearLayout(a);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(a,20),dp(a,20),dp(a,20),dp(a,32));scroll.addView(page);
        scroll.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(0,insets.getSystemWindowInsetTop(),0,insets.getSystemWindowInsetBottom());return insets;});
        add(page,text(a,"aTOMos / RADIO + PACKET STUDIO",12,ACCENT,true),0,10);
        add(page,text(a,title,28,INK,true),0,8);add(page,text(a,subtitle,14,MUTED,false),0,18);a.setContentView(scroll);return page;
    }
    static TextView text(Activity a,String content,int size,int color,boolean bold){TextView t=new TextView(a);t.setText(content);t.setTextSize(size);t.setTextColor(color);t.setLineSpacing(dp(a,3),1);if(bold)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);return t;}
    static TextView body(Activity a,String content){TextView t=text(a,content,14,INK,false);t.setTextIsSelectable(true);return t;}
    static void add(LinearLayout parent,View view,int top,int bottom){float density=parent.getResources().getDisplayMetrics().density;LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(0,Math.round(top*density),0,Math.round(bottom*density));parent.addView(view,p);}
    static LinearLayout card(Activity a,LinearLayout page){LinearLayout card=new LinearLayout(a);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(dp(a,16),dp(a,16),dp(a,16),dp(a,16));GradientDrawable bg=new GradientDrawable();bg.setColor(0xffffffff);bg.setCornerRadius(dp(a,16));card.setBackground(bg);add(page,card,0,14);return card;}
    static Button button(Activity a,LinearLayout parent,String title,Runnable action){Button b=new Button(a);b.setText(title);b.setTextColor(ACCENT);b.setAllCaps(false);b.setOnClickListener(v->action.run());add(parent,b,2,2);return b;}
}
