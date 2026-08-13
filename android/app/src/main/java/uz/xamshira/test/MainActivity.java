package uz.xamshira.test;

import android.os.Bundle;
import android.view.WindowManager;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Skrinshot va ekran yozib olishni bloklaydi, shuningdek so'nggi
        // ilovalar ro'yxatida (recent apps) mazmunni yashiradi — test
        // savol/javoblarining tarqalishining oldini olish uchun.
        getWindow().setFlags(
            WindowManager.LayoutParams.FLAG_SECURE,
            WindowManager.LayoutParams.FLAG_SECURE
        );
    }
}
