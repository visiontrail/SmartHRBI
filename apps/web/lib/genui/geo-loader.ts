import * as echarts from "echarts";

const CHINA_GEO_URL =
  "https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json";

let chinaMapPromise: Promise<boolean> | null = null;

/**
 * Lazily fetch China province GeoJSON and register it with ECharts.
 * Returns true if registration succeeded (or was already done), false on error.
 * The result is cached so subsequent calls resolve immediately.
 */
export function ensureChinaMap(): Promise<boolean> {
  if (chinaMapPromise) {
    return chinaMapPromise;
  }

  chinaMapPromise = (async () => {
    try {
      const resp = await fetch(CHINA_GEO_URL);
      if (!resp.ok) {
        throw new Error(`GeoJSON fetch failed: ${resp.status}`);
      }
      const geoJson = await resp.json();
      echarts.registerMap("china", geoJson as Parameters<typeof echarts.registerMap>[1]);
      return true;
    } catch (err) {
      chinaMapPromise = null;
      console.error("[geo-loader] Failed to load China GeoJSON:", err);
      return false;
    }
  })();

  return chinaMapPromise;
}

const PROVINCE_ALIAS: Record<string, string> = {
  北京: "北京市",
  天津: "天津市",
  上海: "上海市",
  重庆: "重庆市",
  河北: "河北省",
  山西: "山西省",
  辽宁: "辽宁省",
  吉林: "吉林省",
  黑龙江: "黑龙江省",
  江苏: "江苏省",
  浙江: "浙江省",
  安徽: "安徽省",
  福建: "福建省",
  江西: "江西省",
  山东: "山东省",
  河南: "河南省",
  湖北: "湖北省",
  湖南: "湖南省",
  广东: "广东省",
  海南: "海南省",
  四川: "四川省",
  贵州: "贵州省",
  云南: "云南省",
  陕西: "陕西省",
  甘肃: "甘肃省",
  青海: "青海省",
  台湾: "台湾省",
  内蒙古: "内蒙古自治区",
  广西: "广西壮族自治区",
  西藏: "西藏自治区",
  宁夏: "宁夏回族自治区",
  新疆: "新疆维吾尔自治区",
  香港: "香港特别行政区",
  澳门: "澳门特别行政区",
};

/**
 * Normalise province short names (e.g. "北京") to the full name used in the
 * DataV GeoJSON (e.g. "北京市") so ECharts data-to-region matching works.
 */
export function normaliseProvinceName(name: string): string {
  return PROVINCE_ALIAS[name] ?? name;
}
