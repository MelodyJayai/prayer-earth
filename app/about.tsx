import { LegalPage } from "../src/components/LegalPage";

export default function AboutRoute() {
  return (
    <LegalPage
      eyebrow="PRAYER EARTH"
      title="关于祷告地球"
      intro="连接跨越国家与时区的祷告，让真实、经过核实的见证持续带来盼望。"
      sections={[
        {
          heading: "当前版本",
          body: "版本 1.1.0 · Expo 57 · React Native 0.86。当前为离线优先版本，内容服务接入前不会把你发布的祷告上传到服务器。",
        },
        {
          heading: "内容原则",
          body: "全球祷告按紧急、和平、医治、家庭与教会分类；重大见证只有在来源得到核实后才显示核实标记。",
        },
        {
          heading: "开源与许可",
          body: "应用代码、字体、图片和内容在正式发布前需完成版权与授权清单。演示图片不可被视为见证当事人的真实照片。",
        },
      ]}
    />
  );
}
