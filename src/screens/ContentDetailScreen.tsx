import Ionicons from "@expo/vector-icons/Ionicons";
import { Image } from "expo-image";
import { memo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import type { ImportedContentItem } from "../contentData";
import { colors } from "../theme";

export const ContentDetailScreen = memo(function ContentDetailScreen({
  item,
  onBack,
}: {
  item: ImportedContentItem;
  onBack: () => void;
}) {
  const [failed, setFailed] = useState(false);
  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={onBack} style={styles.back}>
          <Ionicons name="arrow-back" size={22} color={colors.ink} />
        </Pressable>
        <View style={styles.headerCopy}>
          <Text style={styles.headerTitle}>{item.channel}</Text>
          <Text style={styles.headerDate}>{item.date}</Text>
        </View>
      </View>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.notice}>
          <Ionicons name="information-circle-outline" size={18} color={colors.green} />
          <Text style={styles.noticeText}>来源：微信群图片导入。内容保持原图，未将缩略图纳入试用版。</Text>
        </View>
        {failed ? (
          <View style={styles.failed}><Ionicons name="image-outline" size={34} color={colors.muted} /><Text style={styles.failedText}>原图暂时无法显示</Text></View>
        ) : (
          <View style={styles.imageStack}>
            {item.segments.map((segment, index) => (
              <Image
                key={`${item.id}-${index}`}
                source={segment.image}
                style={{ width: "100%", aspectRatio: segment.width / segment.height }}
                contentFit="contain"
                cachePolicy="memory-disk"
                onError={() => setFailed(true)}
                accessibilityLabel={`${item.date} ${item.channel}原图第${index + 1}段`}
              />
            ))}
          </View>
        )}
        <Text style={styles.sourceFile}>原文件：{item.sourceFile}</Text>
      </ScrollView>
    </View>
  );
});

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.cream },
  header: { minHeight: 68, flexDirection: "row", alignItems: "center", paddingHorizontal: 15, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.line, backgroundColor: colors.white },
  back: { width: 42, height: 42, alignItems: "center", justifyContent: "center" },
  headerCopy: { marginLeft: 4 },
  headerTitle: { color: colors.ink, fontSize: 17, fontWeight: "800" },
  headerDate: { color: colors.inkSoft, fontSize: 12, marginTop: 2 },
  content: { padding: 15, paddingBottom: 45 },
  notice: { flexDirection: "row", gap: 8, alignItems: "flex-start", backgroundColor: colors.mint, borderRadius: 13, padding: 12, marginBottom: 14 },
  noticeText: { color: colors.greenDark, fontSize: 12, lineHeight: 18, flex: 1 },
  imageStack: { backgroundColor: colors.white, borderRadius: 12, overflow: "hidden" },
  failed: { height: 220, borderRadius: 14, backgroundColor: colors.white, alignItems: "center", justifyContent: "center", gap: 10 },
  failedText: { color: colors.inkSoft, fontSize: 13 },
  sourceFile: { color: colors.muted, fontSize: 11, lineHeight: 17, marginTop: 12 },
});
