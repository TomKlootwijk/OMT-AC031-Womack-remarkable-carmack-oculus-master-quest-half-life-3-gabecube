/* aTOMos frozen-model comparison adapter. Does not perform orbit determination.
 * Orekit/Hipparchus remain external, unmodified Apache-2.0 dependencies.
 */
import com.google.gson.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import org.hipparchus.CalculusFieldElement;
import org.hipparchus.geometry.euclidean.threed.*;
import org.hipparchus.ode.nonstiff.DormandPrince853Integrator;
import org.orekit.forces.ForceModel;
import org.orekit.forces.gravity.*;
import org.orekit.forces.gravity.potential.*;
import org.orekit.frames.*;
import org.orekit.orbits.*;
import org.orekit.propagation.*;
import org.orekit.propagation.numerical.NumericalPropagator;
import org.orekit.time.*;
import org.orekit.utils.*;

public final class OrekitFrozenOrbit {
    static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    static double d(JsonObject o, String k) { return o.get(k).getAsDouble(); }
    static double[] array(JsonArray a) {
        double[] v = new double[a.size()];
        for (int i=0;i<v.length;i++) v[i]=a.get(i).getAsDouble();
        return v;
    }
    static String sha(Path p) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(p)));
    }
    static double[] series(JsonArray segments, double t) {
        JsonObject chosen=null;
        for (JsonElement item:segments) {
            JsonObject s=item.getAsJsonObject();
            if (t>=d(s,"t0_s") && t<=d(s,"t1_s")) chosen=s;
        }
        if(chosen==null) throw new IllegalArgumentException("Outside frozen series: "+t);
        double u=2*(t-d(chosen,"t0_s"))/(d(chosen,"t1_s")-d(chosen,"t0_s"))-1;
        JsonArray rows=chosen.getAsJsonArray("coefficients"); double[] out=new double[rows.size()];
        for(int row=0;row<out.length;row++) {
            JsonArray c=rows.get(row).getAsJsonArray(); double b1=0,b2=0;
            for(int j=c.size()-1;j>0;j--) {double b=2*u*b1-b2+c.get(j).getAsDouble();b2=b1;b1=b;}
            out[row]=u*b1-b2+c.get(0).getAsDouble();
        }
        return out;
    }
    static double[][] product(double[][] a,double[][] b) {
        double[][] r=new double[3][3];
        for(int i=0;i<3;i++)for(int j=0;j<3;j++)for(int k=0;k<3;k++)r[i][j]+=a[i][k]*b[k][j];
        return r;
    }
    static Vector3D apply(double[][] a,Vector3D v,boolean transpose) {
        double[] r=new double[3],p=v.toArray();
        for(int i=0;i<3;i++)for(int j=0;j<3;j++)r[i]+=(transpose?a[j][i]:a[i][j])*p[j];
        return new Vector3D(r);
    }
    static final class FrozenForces implements ForceModel {
        final JsonObject model,force,frame,forcing;
        final AbsoluteDate epoch;
        final double mu,radius,au,srp,light;
        final boolean shadow;
        final double[] empirical;
        final HolmesFeatherstoneAttractionModel gravity;
        final Relativity relativity;
        long calls=0;
        FrozenForces(JsonObject model) {
            this.model=model;force=model.getAsJsonObject("force");frame=model.getAsJsonObject("frame");forcing=model.getAsJsonObject("forcing");
            if(!model.get("profile").getAsString().equals("ORBIT-DYNAMICS-R2"))throw new IllegalArgumentException("R2 required");
            epoch=AbsoluteDate.GPS_EPOCH.shiftedBy(d(model,"epoch_gpst_s"));
            mu=d(force,"mu_m3_s2");radius=d(force,"radius_m");au=d(force,"au_m");srp=d(force,"srp_m_s2_at_au");light=d(force,"c_m_s");
            shadow=force.get("shadow").getAsBoolean();empirical=array(force.getAsJsonArray("empirical_rtn_m_s2"));
            int n=force.get("gravity_degree").getAsInt();double[][] c=new double[n+1][],s=new double[n+1][];
            for(int i=0;i<=n;i++) {
                c[i]=Arrays.copyOf(array(force.getAsJsonArray("gravity_c").get(i).getAsJsonArray()),i+1);
                s[i]=Arrays.copyOf(array(force.getAsJsonArray("gravity_s").get(i).getAsJsonArray()),i+1);
            }
            if(c[0][0]!=1 || s[0][0]!=0 || (n>=1 && (c[1][0]!=0 || c[1][1]!=0 || s[1][0]!=0 || s[1][1]!=0)))
                throw new IllegalArgumentException("HF excludes degree 0/1; require C00=1 and degree 1 zero");
            var raw=GravityFieldFactory.getUnnormalizedProvider(radius,mu,TideSystem.UNKNOWN,c,s);
            gravity=new HolmesFeatherstoneAttractionModel(FramesFactory.getGCRF(),GravityFieldFactory.getNormalizedProvider(raw));
            relativity=force.get("relativity").getAsBoolean()?new Relativity(mu):null;
            if(relativity!=null && light!=Constants.SPEED_OF_LIGHT)throw new IllegalArgumentException("Orekit relativity light speed mismatch");
        }
        double[][] matrix(double t) {
            double[] e=series(frame.getAsJsonArray("eop_segments"),t),qv=series(frame.getAsJsonArray("q_segments"),t);
            double a=d(frame,"era0_rad")+d(frame,"era_rate_rad_s")*t+e[0];
            double c=Math.cos(a),s=Math.sin(a),cx=Math.cos(e[1]),sx=Math.sin(e[1]),cy=Math.cos(e[2]),sy=Math.sin(e[2]);
            double[][] p={{cx,0,sx},{sy*sx,cy,-sy*cx},{-cy*sx,sy,cy*cx}};
            double[][] r={{c,s,0},{-s,c,0},{0,0,1}},q=new double[3][3];
            for(int i=0;i<9;i++)q[i/3][i%3]=qv[i];
            return product(product(p,r),q);
        }
        public Vector3D acceleration(SpacecraftState state,double[] parameters) {
            calls++; double t=state.getDate().durationFrom(epoch);
            Vector3D r=state.getPosition(),v=state.getPVCoordinates().getVelocity();double[][] m=matrix(t);
            Vector3D p=apply(m,r,false);double norm=p.getNorm();
            if(norm<=radius)throw new IllegalArgumentException("Earth intersection");
            // Orekit's independent HF recurrence returns the non-central gradient.
            // The central term is evaluated in the same frozen matrix as R2.
            Vector3D a=apply(m,new Vector3D(gravity.gradient(state.getDate(),p,mu)).add(p.scalarMultiply(-mu/(norm*norm*norm))),true);
            Vector3D sun=new Vector3D(series(forcing.getAsJsonArray("sun"),t));
            for(String bodyName:new String[]{"sun","moon"}) {
                double gm=d(force,bodyName+"_mu_m3_s2");
                if(gm==0)continue;
                Vector3D body=bodyName.equals("sun")?sun:new Vector3D(series(forcing.getAsJsonArray(bodyName),t));
                Vector3D delta=body.subtract(r);
                a=a.add(delta.scalarMultiply(gm/Math.pow(delta.getNorm(),3))).subtract(body.scalarMultiply(gm/Math.pow(body.getNorm(),3)));
            }
            if(srp!=0) {
                Vector3D unit=sun.normalize();double projection=r.dotProduct(unit);
                boolean eclipsed=shadow && projection<0 && r.subtract(unit.scalarMultiply(projection)).getNorm()<radius;
                if(!eclipsed) {Vector3D delta=r.subtract(sun);double dist=delta.getNorm();a=a.add(delta.scalarMultiply(srp*(au/dist)*(au/dist)/dist));}
            }
            if(empirical[0]!=0 || empirical[1]!=0 || empirical[2]!=0) {
                Vector3D radial=r.normalize(),normal=r.crossProduct(v).normalize(),transverse=normal.crossProduct(radial);
                a=a.add(new Vector3D(empirical[0],radial,empirical[1],transverse,empirical[2],normal));
            }
            if(relativity!=null)a=a.add(relativity.acceleration(state,new double[]{mu}));
            return a;
        }
        public boolean dependsOnPositionOnly(){return false;}
        public List<ParameterDriver> getParametersDrivers(){return Collections.emptyList();}
        public <T extends CalculusFieldElement<T>> FieldVector3D<T> acceleration(FieldSpacecraftState<T> s,T[] p) {
            throw new UnsupportedOperationException("Scalar benchmark only; variational/OD equations not implemented");
        }
    }
    static SpacecraftState state(double[] y,AbsoluteDate date,double mu) {
        return new SpacecraftState(new AbsolutePVCoordinates(FramesFactory.getGCRF(),date,new PVCoordinates(new Vector3D(Arrays.copyOfRange(y,0,3)),new Vector3D(Arrays.copyOfRange(y,3,6)))));
    }
    public static void main(String[] args) throws Exception {
        if(args.length<3)throw new IllegalArgumentException("model.json request.json output.json [position_abs_tol_m=1e-6] [max_step_s=60]");
        long begin=System.nanoTime();Path modelPath=Path.of(args[0]),requestPath=Path.of(args[1]);
        JsonObject envelope=JsonParser.parseString(Files.readString(modelPath)).getAsJsonObject();
        JsonObject model=envelope.has("model")?envelope.getAsJsonObject("model"):envelope;
        JsonObject request=JsonParser.parseString(Files.readString(requestPath)).getAsJsonObject();
        double[] times=array(request.getAsJsonArray("times_s"));
        if(times.length==0)throw new IllegalArgumentException("No samples");
        double[] domain=array(model.getAsJsonArray("domain_s"));
        for(int i=0;i<times.length;i++)if(!Double.isFinite(times[i]) || times[i]<0 || times[i]>domain[1] || (i>0 && times[i]<=times[i-1]))throw new IllegalArgumentException("Strict future sorted samples in domain required");
        if(request.has("model_sha256") && !request.get("model_sha256").getAsString().equals(sha(modelPath)))throw new IllegalArgumentException("Frozen model digest mismatch");
        double tol=args.length>3?Double.parseDouble(args[3]):1e-6,maxStep=args.length>4?Double.parseDouble(args[4]):60;
        FrozenForces forces=new FrozenForces(model);
        // Cartesian SI state, separate velocity and mass controls; no element conversion.
        double[] abs={tol,tol,tol,tol*1e-3,tol*1e-3,tol*1e-3,1e-10};
        double[] rel={2e-14,2e-14,2e-14,2e-14,2e-14,2e-14,2e-14};
        DormandPrince853Integrator integrator=new DormandPrince853Integrator(1e-8,maxStep,abs,rel);
        integrator.setInitialStepSize(Math.min(10,maxStep));
        NumericalPropagator propagator=new NumericalPropagator(integrator);
        // Absolute PVA mode adds dr/dt=v independently of the central force.
        // OrbitType.CARTESIAN with no NewtonianAttraction would omit dr/dt.
        propagator.setOrbitType(null);propagator.setIgnoreCentralAttraction(true);
        propagator.setInitialState(state(array(model.getAsJsonArray("state_gcrs")),forces.epoch,forces.mu));
        propagator.addForceModel(forces);
        EphemerisGenerator generator=propagator.getEphemerisGenerator();
        long setup=System.nanoTime();propagator.propagate(forces.epoch.shiftedBy(times[times.length-1]));long propagated=System.nanoTime();
        long integrationCalls=forces.calls;BoundedPropagator ephemeris=generator.getGeneratedEphemeris();
        // Short-time kinematics audit catches a force-only derivative mapping.
        double auditDt=Math.min(0.01,times[times.length-1]);
        SpacecraftState start=propagator.getInitialState();
        // Propagation may reset the initial state to the final state; retain the
        // literal seed here, rather than relying on that mutable property.
        start=state(array(model.getAsJsonArray("state_gcrs")),forces.epoch,forces.mu);
        Vector3D expected=start.getPosition().add(start.getPVCoordinates().getVelocity().scalarMultiply(auditDt)).add(forces.acceleration(start,new double[0]).scalarMultiply(0.5*auditDt*auditDt));
        double kinematicsError=ephemeris.propagate(forces.epoch.shiftedBy(auditDt)).getPosition().distance(expected);
        if(kinematicsError>0.001)throw new IllegalStateException("Short-time position derivative audit failed: "+kinematicsError);
        double[][] states=new double[times.length][6],accelerations=new double[times.length][3];
        for(int i=0;i<times.length;i++) {
            SpacecraftState s=ephemeris.propagate(forces.epoch.shiftedBy(times[i]));PVCoordinates pv=s.getPVCoordinates();
            System.arraycopy(pv.getPosition().toArray(),0,states[i],0,3);System.arraycopy(pv.getVelocity().toArray(),0,states[i],3,3);
            accelerations[i]=forces.acceleration(s,new double[0]).toArray();
        }
        long queried=System.nanoTime();
        Map<String,Object> out=new LinkedHashMap<>();
        out.put("profile","ATOMOS-OREKIT-FROZEN-R2-COMPARISON-R1");out.put("version","Orekit 13.1.8 / Hipparchus 4.0.3");
        out.put("model_sha256",sha(modelPath));out.put("request_sha256",sha(requestPath));
        out.put("times_s",times);out.put("states_gcrs_m_m_s",states);out.put("accelerations_gcrs_m_s2",accelerations);
        out.put("kinematics_audit",Map.of("duration_s",auditDt,"second_order_position_residual_m",kinematicsError,"maximum_admitted_m",0.001));
        out.put("integrator",Map.of("name","DormandPrince853Integrator","position_absolute_tolerance_m",tol,"velocity_absolute_tolerance_m_s",tol*1e-3,"relative_tolerance",2e-14,"max_step_s",maxStep,"min_step_s",1e-8,"force_evaluations",integrationCalls));
        out.put("force_components",List.of("Orekit HolmesFeatherstone gradient with frozen degree/order 12 EGM96 coefficients normalized by Orekit","Explicit central gravity in frozen frame; Orekit automatic central attraction disabled","Independent Java adapters for frozen Sun/Moon differential point mass, cylindrical-shadow SRP, and constant RTN empirical force","Orekit Relativity; frozen speed of light checked"));
        out.put("time_convention","AbsoluteDate.GPS_EPOCH + epoch_gpst_s; SI duration t. Frozen environment evaluated at t, no UTC/EOP downloads or refit.");
        out.put("frame_convention","Geocentric GCRF-labelled Cartesian initial state interpreted as frozen GCRS. Raw frozen P*R*Q maps gravity positions; transpose maps gradients. No frame orthogonalization or fitted alignment.");
        out.put("scope","Independent Orekit numerical integrator and gravity/relativity algorithms, with custom adapters preserving the aTOMos frozen force model. No Orekit orbit determination, new physical model, or universal accuracy comparison.");
        out.put("timing",Map.of("setup_s",(setup-begin)*1e-9,"propagate_s",(propagated-setup)*1e-9,"query_and_acceleration_audit_s",(queried-propagated)*1e-9,"excludes","JVM startup and JSON report serialization"));
        Files.writeString(Path.of(args[2]),GSON.toJson(out)+"\n");
        System.out.println("Orekit: "+times.length+" samples; "+integrationCalls+" force evaluations; "+((propagated-setup)*1e-9)+" propagation seconds");
    }
}
