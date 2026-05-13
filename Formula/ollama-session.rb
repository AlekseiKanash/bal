class OllamaSession < Formula
  desc "LLM Backend Launcher — manage local LLM sessions via ollama or omlx"
  homepage "https://github.com/akanash/ollama-session"
  url "https://github.com/akanash/ollama-session/releases/download/v0.1.0/ollama_session_bal-0.1.0-py3-none-any.whl"
  sha256 "PLACEHOLDER" # update on each release

  license "MIT"
  version "0.1.0" # update on each release

  depends_on "python" => :run

  def install
    system "pip3", "install", "--no-cache-dir", "--no-index",
           "--find-links", Dir.pwd, "ollama_session_bal"
  end

  test do
    system "#{bin}/bal", "--version"
  end
end
