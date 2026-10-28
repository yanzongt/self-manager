import { ref } from "vue";
import {
  clone,
  emptyData,
  readData,
  STORAGE_KEY,
  type StrengthData,
} from "./model";
export function useStrength() {
  const data = ref(emptyData()),
    message = ref("");
  // Never overwrite unreadable storage with defaults; edits are blocked until a valid backup is imported.
  let unreadable = false;
  try {
    data.value = readData();
  } catch {
    unreadable = true;
    message.value =
      "已有数据无法读取，原始存储保持不变。请检查浏览器存储，或导入有效完整备份。";
  }
  function commit(candidate: StrengthData, restore = false) {
    if (unreadable && !restore) {
      message.value = "请先导入有效完整备份以恢复已有数据";
      return false;
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(candidate));
      data.value = candidate;
      unreadable = false;
      return true;
    } catch {
      message.value = "本地保存失败，当前数据未更改";
      return false;
    }
  }
  function update(change: (draft: StrengthData) => void) {
    const draft = clone(data.value);
    change(draft);
    return commit(draft);
  }
  return { data, message, commit, update };
}
