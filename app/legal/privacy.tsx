import { LegalPage } from "../../src/components/LegalPage";

export default function PrivacyRoute() {
  return (
    <LegalPage
      eyebrow="PRIVACY"
      title="隐私与数据说明"
      intro="祷告内容可能涉及信仰、健康与家庭等敏感信息。我们坚持最少收集、清晰告知和由你控制。"
      sections={[
        {
          heading: "当前版本保存什么",
          body: "1.1.0 版本不会要求注册账号。你标记的祷告和自行发布的内容保存在当前设备的本地存储中；卸载应用会删除这些本地记录。",
        },
        {
          heading: "网络与图片",
          body: "见证配图通过 HTTPS 从内容分发网络加载并在设备上缓存。正式接入全球内容服务前，我们会另行说明服务器位置、保存期限与删除方式。",
        },
        {
          heading: "你的选择",
          body: "请不要提交真实姓名、地址、联系方式、病历编号等可识别个人的信息。未来启用账号或云同步时，应用内将提供数据导出和删除入口。",
        },
        {
          heading: "联系我们",
          body: "正式发布前，运营方将在此处补充可验证的隐私联系邮箱与官方网站。商店提交前不得保留此占位说明。",
        },
      ]}
    />
  );
}
