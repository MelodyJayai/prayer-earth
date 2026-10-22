import { LegalPage } from "../../src/components/LegalPage";

export default function CommunityRoute() {
  return (
    <LegalPage
      eyebrow="COMMUNITY"
      title="祷告社区守则"
      intro="我们希望每一条祷告都传递尊重、真实与盼望。发布即表示你愿意遵守以下守则。"
      sections={[
        {
          heading: "保护隐私",
          body: "不得公开他人的真实姓名、联系方式、精确住址、医疗记录或其他敏感身份信息；涉及未成年人时尤其需要谨慎。",
        },
        {
          heading: "尊重与安全",
          body: "不得发布仇恨、骚扰、威胁、歧视、色情、欺诈、违法或鼓励自我伤害的内容，也不得借祷告募集未经核实的款项。",
        },
        {
          heading: "真实见证",
          body: "见证应基于真实经历。医疗相关内容不得替代专业诊疗，不应承诺确定疗效。被标记为“已核实”的内容必须保留审核记录和来源。",
        },
        {
          heading: "审核与处置",
          body: "正式公开发布功能启用后，内容会进入审核流程；用户可举报内容和屏蔽账号。违反守则的内容可能被隐藏或删除。",
        },
      ]}
    />
  );
}
