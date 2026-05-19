class Bal < Formula
  include Language::Python::Virtualenv

  desc "LLM Backend Launcher — one entry point for multiple LLM backends such as Ollama and oMLX."
  homepage "https://github.com/akanash/bal"

  # Local wheel for testing. Before releasing, replace with:
  #   url "https://github.com/akanash/bal/releases/download/vX.Y.Z/bal-X.Y.Z-py3-none-any.whl"
  #   sha256 "<sha256 of that wheel>"
  #   version "X.Y.Z"
  url "file:///Users/akanash/Projects/bal/dist/bal-0.1.dev33+g645e6340b.d20260514-py3-none-any.whl"
  sha256 "b0a4ea44a57ca2893b27b740a5ea9539e15dc0c89b4c57bba823b9dcaf0938ae"
  version "0.1.0"

  license "MIT"

  depends_on "python@3.13"

  resource "psutil" do
    url "https://files.pythonhosted.org/packages/source/p/psutil/psutil-7.2.2.tar.gz"
    sha256 "0746f5f8d406af344fd547f1c8daa5f5c33dbc293bb8d6a16d80b4bb88f59372"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"bal", "--version"
  end
end
