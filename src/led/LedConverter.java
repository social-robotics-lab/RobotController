package led;

import java.util.HashMap;
import java.util.Map;

import org.json.JSONObject;

import main.Params;

public class LedConverter {

	public static Map<Byte, Short> jsonToMap(JSONObject obj) {
		if (Params.robotType.equals("Sota")) {
			return LedConverter_Sota.jsonToMap(obj);
		} else if (Params.robotType.equals("CommU")) {
			return LedConverter_CommU.jsonToMap(obj);
		} else {
			return new HashMap<Byte, Short>();
		}
	}

	public static JSONObject mapToJson(Map<Byte, Short> map) {
		if (Params.robotType.equals("Sota")) {
			return LedConverter_Sota.mapToJson(map);
		} else if (Params.robotType.equals("CommU")) {
			return LedConverter_CommU.mapToJson(map);
		} else {
			return new JSONObject();
		}
	}

}
