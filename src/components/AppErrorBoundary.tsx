import Ionicons from "@expo/vector-icons/Ionicons";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors } from "../theme";

type Props = { children: ReactNode };
type State = { failed: boolean };

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (__DEV__)
      console.error("Prayer Earth render error", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <View style={styles.container}>
        <View style={styles.icon}>
          <Ionicons name="refresh-outline" size={30} color={colors.green} />
        </View>
        <Text accessibilityRole="header" style={styles.title}>
          页面暂时没有加载成功
        </Text>
        <Text style={styles.body}>
          你的祷告记录仍保存在本机，可以重新载入页面。
        </Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => this.setState({ failed: false })}
          style={styles.button}
        >
          <Text style={styles.buttonText}>重新载入</Text>
        </Pressable>
      </View>
    );
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.cream,
    alignItems: "center",
    justifyContent: "center",
    padding: 28,
  },
  icon: {
    width: 62,
    height: 62,
    borderRadius: 31,
    backgroundColor: colors.mint,
    alignItems: "center",
    justifyContent: "center",
  },
  title: { fontSize: 21, fontWeight: "700", color: colors.ink, marginTop: 18 },
  body: {
    fontSize: 14,
    lineHeight: 22,
    color: colors.inkSoft,
    textAlign: "center",
    marginTop: 8,
  },
  button: {
    minHeight: 48,
    marginTop: 22,
    paddingHorizontal: 24,
    borderRadius: 24,
    backgroundColor: colors.green,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonText: { color: colors.white, fontSize: 14, fontWeight: "700" },
});
