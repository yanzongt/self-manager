import type { Exercise, Routine } from "./model";
export const DAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
export const DAY_ORDER = [1, 2, 3, 4, 5, 6, 0];
let EX = [
  ["squat", "徒手深蹲", "腿部", "3×12", "0", "保持动作控制；前2周减少组数。"],
  [
    "split",
    "保加利亚分腿蹲",
    "腿部",
    "每腿3×8",
    "0",
    "扶稳，后脚置于牢固矮凳。",
  ],
  ["bridge", "单腿臀桥", "臀部", "每腿3×10", "0", "顶端停顿2秒。"],
  ["calf", "单腿提踵", "小腿", "每腿3×15", "0", "扶墙缓慢上下。"],
  ["deadbug", "死虫式", "核心", "每侧3×10", "0", "保持腰背稳定。"],
  [
    "wallpush",
    "墙面/高位俯卧撑",
    "胸肩",
    "2×8–12",
    "0",
    "右肘不适则提高支撑面或停止。",
  ],
  [
    "floorpress",
    "中立握哑铃地板卧推",
    "胸肩",
    "2×10",
    "1",
    "初始每手1–2kg，需先无痛测试。",
  ],
  ["lateral", "哑铃侧平举", "肩部", "2×12", "0.5", "从0.5–1kg测试；不可甩动。"],
  ["scap", "肩胛后缩", "上背", "2×15", "0", "无负重，练习肩胛控制。"],
  [
    "wrist",
    "腕伸肌康复",
    "右肘康复",
    "等长3–5×20–30秒",
    "0",
    "初始等长抗阻；后续逐步加入0–0.5kg慢速训练。",
  ],
  ["hinge", "徒手早安式", "后链", "3×12", "0", "髋向后推，背部中立。"],
  ["step", "登阶", "腿部", "每腿3×10", "0", "20–40cm稳固台阶，量力而行。"],
  [
    "singleRDL",
    "单腿罗马尼亚硬拉",
    "后链",
    "每腿3×8",
    "0",
    "先徒手，维持骨盆水平。",
  ],
  ["reverse", "反向卷腹", "腹部", "3×12", "0", "缓慢控制骨盆运动。"],
  ["bentcalf", "屈膝提踵", "小腿", "每腿2×15", "0", "缓慢完成。"],
  ["ytw", "俯卧Y-T-W抬臂", "上背", "每种2×8", "0", "不持重，肩胛发力。"],
  [
    "bandrow",
    "轻阻力弹力带划船",
    "背部",
    "2×12",
    "0",
    "与哑铃划船二选一，若肘疼则跳过。",
  ],
  [
    "dbrow",
    "单臂哑铃划船",
    "背部",
    "每侧2×10",
    "1",
    "右手从1–2kg试探；与弹力带划船二选一。",
  ],
  ["fly", "俯身反向飞鸟", "肩背", "2×12", "0", "0–0.5kg起步，右肘不适则空手。"],
].map((a) => ({
  id: a[0],
  name: a[1],
  part: a[2],
  prescription: a[3],
  weight: Number(a[4]),
  note: a[5],
}));
export const DEFAULT_ROUTINES: Record<number, Routine> = {
  0: {
    title: "休息与恢复",
    purpose: "完全休息或散步；关注睡眠、关节恢复。",
    ids: [],
  },
  1: {
    title: "下肢A · 深蹲与股四头肌",
    purpose: "以膝主导下肢力量、单腿控制、臀部和核心稳定为主。",
    ids: ["squat", "split", "bridge", "calf", "deadbug"],
  },
  2: {
    title: "上肢A · 胸肩与肘康复",
    purpose: "轻负荷胸肩推力与肩胛控制；严格监测右肘疼痛。",
    ids: ["wallpush", "floorpress", "lateral", "scap", "wrist"],
  },
  3: {
    title: "主动恢复日",
    purpose: "轻度有氧、拉伸或散步；不安排高强度力量训练。",
    ids: [],
  },
  4: {
    title: "下肢B · 后链与腰腹",
    purpose: "臀腿后侧、单腿平衡、腹部力量与稳定性。",
    ids: ["hinge", "step", "singleRDL", "reverse", "deadbug", "bentcalf"],
  },
  5: {
    title: "上肢B · 背肩与肘康复",
    purpose: "肩胛和背部练习；两种划船二选一，优先无痛。",
    ids: ["ytw", "bandrow", "dbrow", "fly", "wrist"],
  },
  6: {
    title: "适量篮球 / 有氧",
    purpose: "注意篮球运动对右肘及小腿的总负荷；若症状加重则减量。",
    ids: [],
  },
};
export const DEFAULT_EX: Exercise[] = EX.map((x) => {
  const n = x.prescription.match(/(\d+)(?:–\d+)?×(\d+)/)!;
  const { prescription, ...fields } = x;
  const side = prescription.match(/每腿|每侧|每种/);
  return {
    ...fields,
    note: (side ? side[0] + "分别完成。" : "") + x.note,
    sets: Number(n[1]),
    reps: Number(n[2]),
    guide: "",
    unit: prescription.includes("秒") ? "秒" : "次",
  };
});
