package servo;

import java.util.HashMap;
import java.util.Map;

import org.json.JSONObject;

public class ServoConverter_Sota {

	private static final double REDUCTION_RATIO_BODY_Y = 2.429;
	private static final double REDUCTION_RATIO_HEAD_Y = 1.75;
	private static final double REDUCTION_RATIO_HEAD_R = 1.75;
	private static final Map<String, Byte> map = new HashMap<String, Byte>() {
		{
			put("BODY_Y", (byte) 1);
			put("L_SHOU", (byte) 2);
			put("L_ELBO", (byte) 3);
			put("R_SHOU", (byte) 4);
			put("R_ELBO", (byte) 5);
			put("HEAD_Y", (byte) 6);
			put("HEAD_P", (byte) 7);
			put("HEAD_R", (byte) 8);
		}
	};

	public static Map<Byte, Short> jsonToMap(JSONObject json) {
		Map<Byte, Short> ret = new HashMap<Byte, Short>();
		for (String key : json.keySet()) {
			byte id = map.get(key);
			int val = json.getInt(key);
			switch (key) {
			case "BODY_Y": // -61 ~ 61 (servo: -150 ~ 150)
			    if      (val < -61) ret.put(id, (short) (-61 * 10 * REDUCTION_RATIO_BODY_Y));
			    else if (val >  61) ret.put(id, (short) ( 61 * 10 * REDUCTION_RATIO_BODY_Y));
			    else                ret.put(id, (short) (val * 10 * REDUCTION_RATIO_BODY_Y));
			    continue;
			case "L_SHOU": // -180 ~ 60
			    if      (val < -180) ret.put(id, (short) (-180 * 10));
			    else if (val >   60) ret.put(id, (short) (  60 * 10));
			    else                 ret.put(id, (short) ( val * 10));
			    continue;
			case "L_ELBO": // -90 ~ 65
			    if      (val < -90) ret.put(id, (short) (-90 * 10));
			    else if (val >  65) ret.put(id, (short) ( 65 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "R_SHOU": // -60 ~ 180
			    if      (val < -60) ret.put(id, (short) (-60 * 10));
			    else if (val > 180) ret.put(id, (short) (180 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "R_ELBO": // -65 ~ 90
			    if      (val < -65) ret.put(id, (short) (-65 * 10));
			    else if (val >  90) ret.put(id, (short) ( 90 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "HEAD_Y": // -85 ~ 85 (servo: -150 ~ 150)
			    if      (val < -85) ret.put(id, (short) (-85 * 10 * REDUCTION_RATIO_HEAD_Y));
			    else if (val >  85) ret.put(id, (short) ( 85 * 10 * REDUCTION_RATIO_HEAD_Y));
			    else                ret.put(id, (short) (val * 10 * REDUCTION_RATIO_HEAD_Y));
			    continue;
			case "HEAD_P": // -27 ~ 5
			    if      (val < -27) ret.put(id, (short) (-27 * 10));
			    else if (val >   5) ret.put(id, (short) (  5 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "HEAD_R": // -30 ~ 30
			    if      (val < -30) ret.put(id, (short) (-30 * 10 * REDUCTION_RATIO_HEAD_R));
			    else if (val >  30) ret.put(id, (short) ( 30 * 10 * REDUCTION_RATIO_HEAD_R));
			    else                ret.put(id, (short) (val * 10 * REDUCTION_RATIO_HEAD_R));
			    continue;
			}
		}
		return ret;
	}

	public static JSONObject mapToJson(Map<Byte, Short> map) {
		JSONObject ret = new JSONObject();
		for (Byte id : map.keySet()) {
			int val = map.get(id).intValue();
			switch (id) {
			case 1:
				ret.put("BODY_Y", (int) (val / 10 / REDUCTION_RATIO_BODY_Y));
				continue;
			case 2:
				ret.put("L_SHOU", (int) (val / 10));
				continue;
			case 3:
				ret.put("L_ELBO", (int) (val / 10));
				continue;
			case 4:
				ret.put("R_SHOU", (int) (val / 10));
				continue;
			case 5:
				ret.put("R_ELBO", (int) (val / 10));
				continue;
			case 6:
				ret.put("HEAD_Y", (int) (val / 10 / REDUCTION_RATIO_HEAD_Y));
				continue;
			case 7:
				ret.put("HEAD_P", (int) (val / 10));
				continue;
			case 8:
				ret.put("HEAD_R", (int) (val / 10 / REDUCTION_RATIO_HEAD_R));
				continue;
			}
		}
		return ret;
	}
}
