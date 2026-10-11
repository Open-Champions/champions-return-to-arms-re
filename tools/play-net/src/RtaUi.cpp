// What this build adds to the application's windows. See Rta.h.
#include "Rta.h"

#include <QAction>
#include <QDialog>
#include <QDialogButtonBox>
#include <QLabel>
#include <QMainWindow>
#include <QMenu>
#include <QMenuBar>
#include <QPointer>
#include <QTimer>
#include <QVBoxLayout>

#include "AppConfig.h"

#define PREF_RTA_CONTROLS_SHOWN "rta.ui.controlsshown"

namespace
{
	// The keyboard as ControllerConfigDialog::AutoConfigureKeyboard sets it up (see
	// play-net.patch), and the controller as RtaPad.mm reads it. Keep the three in step.
	QString ControlsText()
	{
		QString controller = QString::fromStdString(Rta::GamePadName());
		QString text;
		text += "<h3>Controller</h3>";
		if(controller.isEmpty())
			text += "<p>No game controller is attached. Plug one in (USB) or pair it (Bluetooth) at any time - "
			        "DualSense, DualShock 4, Xbox, Switch Pro and others that macOS knows work at once, with nothing to set up: "
			        "sticks, direction pad and buttons are where they are on a PlayStation pad; Options or Menu is Start, "
			        "Create, Share or View is Select (so is pressing a Sony pad's touchpad).</p>";
		else
			text += QString("<p><b>%1</b> is attached and is the pad in port 1: sticks, direction pad and buttons are where they "
			                "are on a PlayStation pad; Options or Menu is Start, Create, Share or View is Select (so is pressing "
			                "a Sony pad's touchpad). It is listened to while this window is in front.</p>")
			            .arg(controller.toHtmlEscaped());
		text += "<h3>Keyboard</h3>"
		        "<table cellspacing='0' cellpadding='3'>"
		        "<tr><td><b>Move</b> (left stick)</td><td>W&nbsp;A&nbsp;S&nbsp;D</td><td width='24'></td><td><b>Direction pad</b> (menus)</td><td>arrow keys</td></tr>"
		        "<tr><td>&#10005; cross</td><td>K</td><td></td><td>&#9675; circle</td><td>L</td></tr>"
		        "<tr><td>&#9633; square</td><td>J</td><td></td><td>&#9651; triangle</td><td>I</td></tr>"
		        "<tr><td>L1</td><td>Q</td><td></td><td>R1</td><td>E</td></tr>"
		        "<tr><td>L2</td><td>1</td><td></td><td>R2</td><td>3</td></tr>"
		        "<tr><td>L3 (press left stick)</td><td>X</td><td></td><td>R3 (press right stick)</td><td>C</td></tr>"
		        "<tr><td>Camera (right stick)</td><td>T&nbsp;F&nbsp;G&nbsp;H</td><td></td><td>Start / Select</td><td>Return / Backspace</td></tr>"
		        "</table>"
		        "<p>The four face buttons lie on I&nbsp;J&nbsp;K&nbsp;L as they lie on the pad: I on top, J left, K below, L right.<br>"
		        "Full screen: double-click the picture; Escape leaves it.<br>"
		        "Other keys, or a controller macOS does not know: <i>Settings &rarr; Controller Manager</i>.</p>";
		return text;
	}

	QPointer<QDialog> g_controls;
}

void Rta::ShowControls(QWidget* parent)
{
	if(g_controls)
	{
		g_controls->raise();
		g_controls->activateWindow();
		return;
	}
	auto dialog = new QDialog(parent);
	dialog->setAttribute(Qt::WA_DeleteOnClose, true);
	dialog->setWindowTitle("Controls");
	auto layout = new QVBoxLayout(dialog);
	auto label = new QLabel(ControlsText(), dialog);
	label->setTextFormat(Qt::RichText);
	label->setWordWrap(true);
	label->setMinimumWidth(520);
	layout->addWidget(label);
	auto buttons = new QDialogButtonBox(QDialogButtonBox::Close, dialog);
	QObject::connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::close);
	layout->addWidget(buttons);
	// the controller's name follows what is attached while the window is open
	auto timer = new QTimer(dialog);
	QObject::connect(timer, &QTimer::timeout, label, [label]() {
		auto text = ControlsText();
		if(label->text() != text) label->setText(text);
	});
	timer->start(1000);
	g_controls = dialog;
	// not modal: the game goes on, and the keys can be tried while it is read
	dialog->show();
}

void Rta::SetupWindow(QWidget* window)
{
	auto mainWindow = qobject_cast<QMainWindow*>(window);
	if(!mainWindow) return;
	auto helpMenu = mainWindow->findChild<QMenu*>("menuHelp");
	if(!helpMenu) helpMenu = mainWindow->menuBar()->addMenu("Help");
	auto controls = new QAction("Controls...", mainWindow);
	controls->setMenuRole(QAction::NoRole);
	QObject::connect(controls, &QAction::triggered, mainWindow, [mainWindow]() { Rta::ShowControls(mainWindow); });
	helpMenu->insertAction(helpMenu->actions().isEmpty() ? nullptr : helpMenu->actions().first(), controls);

	// once per data directory, a moment after the first start: the keys. Not in test runs.
	auto& config = CAppConfig::GetInstance();
	config.RegisterPreferenceBoolean(PREF_RTA_CONTROLS_SHOWN, false);
	if(!config.GetPreferenceBoolean(PREF_RTA_CONTROLS_SHOWN) && !Rta::IsTestRun())
	{
		config.SetPreferenceBoolean(PREF_RTA_CONTROLS_SHOWN, true);
		QTimer::singleShot(2500, mainWindow, [mainWindow]() { Rta::ShowControls(mainWindow); });
	}
}
