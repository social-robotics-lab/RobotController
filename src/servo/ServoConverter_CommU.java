package servo;

import java.util.HashMap;
import java.util.Map;

import org.json.JSONObject;

public class ServoConverter_CommU {

	private static final double REDUCTION_RATIO_BODY_P   = 3.833;
	private static final double REDUCTION_RATIO_L_SHOU_P = 1.364;
	private static final double REDUCTION_RATIO_R_SHOU_P = 1.364;
	private static final double REDUCTION_RATIO_HEAD_R   = 4.333;
	private static final Map<String, Byte> map = new HashMap<String, Byte>() {
		{
			put("BODY_P",   (byte)  1);
			put("BODY_Y",   (byte)  2);
			put("L_SHOU_P", (byte)  3);
			put("L_SHOU_R", (byte)  4);
			put("R_SHOU_P", (byte)  5);
			put("R_SHOU_R", (byte)  6);
			put("HEAD_P",   (byte)  7);
			put("HEAD_R",   (byte)  8);
			put("HEAD_Y",   (byte)  9);
			put("EYES_P",   (byte) 10);
			put("L_EYE_Y",  (byte) 11);
			put("R_EYE_Y",  (byte) 12);
			put("EYELID",   (byte) 13);
			put("MOUTH",    (byte) 14);
		}
	};

	public static Map<Byte, Short> jsonToMap(JSONObject json) {
		Map<Byte, Short> ret = new HashMap<Byte, Short>();
		for (String key : json.keySet()) {
			byte id = map.get(key);
			int val = json.getInt(key);
			switch (key) {
			case "BODY_P": // -15 ~ 15
				if      (val < -15) ret.put(id, (short) (-15 * 10 * REDUCTION_RATIO_BODY_P));
				else if (val >  15) ret.put(id, (short) ( 15 * 10 * REDUCTION_RATIO_BODY_P));
				else                ret.put(id, (short) (val * 10 * REDUCTION_RATIO_BODY_P));
				continue;
			case "BODY_Y": // -67 ~ 67
				if      (val < -67) ret.put(id, (short) (-67 * 10));
				else if (val >  67) ret.put(id, (short) ( 67 * 10));
				else                ret.put(id, (short) (val * 10));
				continue;
			case "L_SHOU_P": // -108 ~ 108
				if      (val < -108) ret.put(id, (short) (-108 * 10 * REDUCTION_RATIO_L_SHOU_P));
				else if (val >  108) ret.put(id, (short) ( 108 * 10 * REDUCTION_RATIO_L_SHOU_P));
				else                 ret.put(id, (short) ( val * 10 * REDUCTION_RATIO_L_SHOU_P));
				continue;
			case "L_SHOU_R": // -45 ~ 30
				if      (val < -45) ret.put(id, (short) (-45 * 10));
				else if (val >  30) ret.put(id, (short) ( 30 * 10));
				else                ret.put(id, (short) (val * 10));
				continue;
			case "R_SHOU_P": // -108 ~ 108
				if      (val < -108) ret.put(id, (short) (-108 * 10 * REDUCTION_RATIO_R_SHOU_P));
				else if (val >  108) ret.put(id, (short) ( 108 * 10 * REDUCTION_RATIO_R_SHOU_P));
				else                 ret.put(id, (short) ( val * 10 * REDUCTION_RATIO_R_SHOU_P));
				continue;
			case "R_SHOU_R": // -30 ~ 45
				if      (val < -30) ret.put(id, (short) (-30 * 10));
				else if (val >  45) ret.put(id, (short) ( 45 * 10));
				else                ret.put(id, (short) (val * 10));
				continue;
			case "HEAD_P": // -20 ~ 25
				if      (val < -20) ret.put(id, (short) (-20 * 10));
				else if (val >  25) ret.put(id, (short) ( 25 * 10));
				else                ret.put(id, (short) (val * 10));
				continue;
			case "HEAD_R": // -15 ~ 15
				if      (val < -15) ret.put(id, (short) (-15 * 10 * REDUCTION_RATIO_HEAD_R));
				else if (val >  15) ret.put(id, (short) ( 15 * 10 * REDUCTION_RATIO_HEAD_R));
				else                ret.put(id, (short) (val * 10 * REDUCTION_RATIO_HEAD_R));
				continue;
			case "HEAD_Y": // -85 ~ 85
				if      (val < -85) ret.put(id, (short) (-85 * 10));
				else if (val >  85) ret.put(id, (short) ( 85 * 10));
				else                ret.put(id, (short) (val * 10));
				continue;
			case "EYES_P": // -22 ~ 22
				if      (val < -22) ret.put(id, (short) (-22 * 10));
				else if (val >  22) ret.put(id, (short) ( 22 * 10));
				else                ret.put(id, (short) (val * 10));
				continue;
			case "L_EYE_Y": // -35 ~ 20
				if      (val < -35) ret.put(id, (short) (-35 * 10));
				else if (val >  20) ret.put(id, (short) ( 20 * 10));
				else                ret.put(id, (short) (val * 10));
				continue;
			case "R_EYE_Y": // -20 ~ 35
				if      (val < -20) ret.put(id, (short) (-20 * 10));
				else if (val >  35) ret.put(id, (short) ( 35 * 10));
				else                ret.put(id, (short) (val * 10));
				continue;
			case "EYELID": //  -65 ~ 3
				if      (val < -65) ret.put(id, (short) (-65 * 10));
				else if (val >   3) ret.put(id, (short) (  3 * 10));
				else                ret.put(id, (short) (val * 10));
				continue;
			case "MOUTH": // -3 ~ 55
				if      (val < -3) ret.put(id, (short) ( -3 * 10));
				else if (val > 55) ret.put(id, (short) ( 55 * 10));
				else               ret.put(id, (short) (val * 10));
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
				ret.put("BODY_P", (int) (val / 10 / REDUCTION_RATIO_BODY_P));
				continue;
			case 2:
				ret.put("BODY_Y", (int) (val / 10));
				continue;
			case 3:
				ret.put("L_SHOU_P", (int) (val / 10 / REDUCTION_RATIO_L_SHOU_P));
				continue;
			case 4:
				ret.put("L_SHOU_R", (int) (val / 10));
				continue;
			case 5:
				ret.put("R_SHOU_P", (int) (val / 10 / REDUCTION_RATIO_R_SHOU_P));
				continue;
			case 6:
				ret.put("R_SHOU_R", (int) (val / 10));
				continue;
			case 7:
				ret.put("HEAD_P", (int) (val / 10));
				continue;
			case 8:
				ret.put("HEAD_R", (int) (val / 10 / REDUCTION_RATIO_HEAD_R));
				continue;
			case 9:
				ret.put("HEAD_Y", (int) (val / 10));
				continue;
			case 10:
				ret.put("EYES_P", (int) (val / 10));
				continue;
			case 11:
				ret.put("L_EYE_Y", (int) (val / 10));
				continue;
			case 12:
				ret.put("R_EYE_Y", (int) (val / 10));
				continue;
			case 13:
				ret.put("EYELID", (int) (val / 10));
				continue;
			case 14:
				ret.put("MOUTH", (int) (val / 10));
				continue;
			}
		}
		return ret;
	}

}
