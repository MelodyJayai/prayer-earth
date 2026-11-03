import { memo } from "react";
import { StyleSheet, Text, View } from "react-native";

export const DemoDataNotice = memo(function DemoDataNotice() {
  return (
    <View accessibilityRole="text" style={styles.notice}>
      <Text style={styles.title}>演示数据·未联网</Text>
      <Text style={styles.body}>
        条目和人数来自随包种子与本机发布，没有连接服务器，也不会同步到其他设备。
      </Text>
    </View>
  );
});

const styles = StyleSheet.create({
  notice: {
    backgroundColor: "#F3E7D4",
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 14,
  },
  title: {
    fontSize: 13,
    fontWeight: "800",
    color: "#6E4E16",
    letterSpacing: 0.2,
  },
  body: {
    fontSize: 12,
    lineHeight: 18,
    color: "#6B5840",
    marginTop: 4,
  },
});
