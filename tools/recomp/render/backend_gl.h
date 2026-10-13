// backend_gl.h - the OpenGL backend (backend_gl.cpp).  Make it, and call it, with an
// OpenGL 4.1 core (or newer) context current.
#pragma once
#include "backend.h"

namespace render {

class GlBackend : public Backend {
  public:
    GlBackend();
    ~GlBackend() override;
    void set_output_size(int width, int height) override;
    void execute(const FrameList& frame) override;
    void present(int width, int height, double aspect) override;
    // The same into a framebuffer whose first row is the top one (a surface shown by Metal:
    // app/present_host.h); present() is for one whose first row is the bottom (OpenGL's own window).
    void present_top_down(int width, int height, double aspect);
    bool read_shown(std::vector<uint8_t>& rgba, int& width, int& height) override;
    bool read_target(uint32_t id, std::vector<uint8_t>& rgba, int& width, int& height);
    uint64_t draw_calls() const;
    // Multisampling, mip maps, anisotropic filtering, replacement pictures.  Once, before the first list.
    void configure(const PictureOptions& options);
    PictureFigures figures() const;
    void set_replacements(bool on);     // draw with the game's own textures again (the same frame with and without)

  private:
    struct Impl;
    Impl* impl;
    void present_to(int width, int height, double aspect, bool top_down);
};

}  // namespace render
