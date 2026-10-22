import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { ScreenFrame } from "../../src/components/ScreenFrame";
import { useContentFeed } from "../../src/hooks/useContentFeed";
import { ContentDetailScreen } from "../../src/screens/ContentDetailScreen";
import { colors } from "../../src/theme";

export default function ContentDetailRoute() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { items, hasChecked, refreshing, refresh, error } = useContentFeed();
  const item = items.find((content) => content.id === id);
  const back = () => router.canGoBack() ? router.back() : router.replace("/testimonies");
  return (
    <ScreenFrame>
      {() => item ? (
        <ContentDetailScreen item={item} onBack={back} />
      ) : (
        <View style={styles.empty}>
          <Text style={styles.title}>{!hasChecked || refreshing ? "正在获取这条内容…" : error ? "暂时无法获取这条内容" : "这条内容尚未发布或已下架"}</Text>
          {hasChecked && !refreshing && <Pressable accessibilityRole="button" onPress={refresh}><Text style={styles.link}>重新获取</Text></Pressable>}
          <Pressable accessibilityRole="button" onPress={back}><Text style={styles.link}>返回内容库</Text></Pressable>
        </View>
      )}
    </ScreenFrame>
  );
}

const styles = StyleSheet.create({
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: 20 },
  title: { color: colors.ink, fontSize: 18, fontWeight: "700" },
  link: { color: colors.green, padding: 12 },
});
