import { useState } from "react";
import Drawer from "../../components/ui/Drawer";
import ManualExperienceForm from "../../components/ManualExperienceForm";
import { useToast } from "../../components/ui/Toast";

interface Props {
  open: boolean;
  onClose: () => void;
  /** 保存成功后回调，让 Chat 提示 AI 会在对话里提到这些经历 */
  onSaved?: () => void;
}

// 轻量经历模板：作为对话输入框旁的辅助入口，而非独立中间页。
// 复用现有 ManualExperienceForm（业务逻辑不变），提交走 /experience 手动录入。
export default function ExperienceTemplateDrawer({ open, onClose, onSaved }: Props) {
  const toast = useToast();
  const [done, setDone] = useState(false);

  const handleSaved = () => {
    setDone(true);
    toast.success("已记录你的经历，我们接着聊");
    onSaved?.();
    // 延迟关闭，让用户看到成功提示
    window.setTimeout(() => {
      setDone(false);
      onClose();
    }, 700);
  };

  return (
    <Drawer open={open} onClose={onClose} title="填写你的经历">
      <p className="onb-drawer-sub">
        这是辅助录入。填完你会跳回对话，AI 会在接下来的聊天里自然地提到这些内容。
      </p>
      {done ? (
        <div className="onb-drawer-done">已保存 ✓</div>
      ) : (
        <ManualExperienceForm onSaved={handleSaved} />
      )}
    </Drawer>
  );
}
